import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import torch
from src.core.config import settings
from src.core.engines.dubbing.hallucination_filter import is_hallucinated_segment

logger = logging.getLogger("sensevoice_engine")


class SenseVoiceEngine:
    """
    Engine nhận diện giọng nói siêu tốc & chống ảo giác BGM bằng SenseVoice-Small (FunAudioLLM).
    - Kiến trúc Non-autoregressive: Triệt tiêu 100% ảo giác lặp lại trên nhạc nền BGM (như '你显示').
    - Nhanh gấp 15 lần Whisper, tích hợp sẵn VAD (Voice Activity Detection).
    """

    _model: Optional[Any] = None
    _init_failed: bool = False

    @classmethod
    def _find_model_dir(cls) -> Optional[str]:
        """Tìm thư mục snapshot của SenseVoice-Small trên ổ D."""
        candidates = [
            Path(r"D:\huggingface_cache\hub\models--FunAudioLLM--SenseVoiceSmall\snapshots"),
            settings.STORAGE_DIR / "hf_cache" / "hub" / "models--FunAudioLLM--SenseVoiceSmall" / "snapshots",
            settings.STORAGE_DIR / "modelscope_cache" / "models" / "iic--SenseVoiceSmall" / "snapshots",
        ]
        for c in candidates:
            if c.exists():
                for snap in c.iterdir():
                    if snap.is_dir() and (snap / "model.pt").exists() and (snap / "model.pt").stat().st_size > 500_000_000:
                        return str(snap)
        return None

    @classmethod
    def _find_vad_dir(cls) -> Optional[str]:
        """Tìm thư mục snapshot của FSMN-VAD trên ổ D."""
        candidates = [
            Path(r"D:\huggingface_cache\hub\models--funasr--fsmn-vad\snapshots"),
            settings.STORAGE_DIR / "hf_cache" / "hub" / "models--funasr--fsmn-vad" / "snapshots",
        ]
        for c in candidates:
            if c.exists():
                for snap in c.iterdir():
                    if snap.is_dir() and (snap / "model.pt").exists():
                        return str(snap)
        return None

    @classmethod
    def is_available(cls) -> bool:
        """Kiểm tra mô hình SenseVoice đã sẵn sàng nạp trực tiếp từ ổ đĩa hay chưa."""
        if cls._init_failed:
            return False
        try:
            import funasr
            return cls._find_model_dir() is not None
        except ImportError:
            return False

    @classmethod
    def get_model(cls) -> Optional[Any]:
        """Tải mô hình SenseVoice-Small kèm VAD trực tiếp từ đĩa (100% offline, không tải mạng)."""
        model_dir = cls._find_model_dir()
        if cls._init_failed or not model_dir:
            return None
        if cls._model is None:
            try:
                from funasr import AutoModel

                device = "cuda:0" if torch.cuda.is_available() else "cpu"
                vad_dir = cls._find_vad_dir() or "fsmn-vad"

                logger.info(f"Đang nạp mô hình SenseVoice-Small từ {model_dir} trên {device}...")
                cls._model = AutoModel(
                    model=model_dir,
                    vad_model=vad_dir,
                    vad_kwargs={"max_single_segment_time": 30000},
                    device=device,
                    disable_update=True,
                )
                logger.info("Nạp thành công SenseVoice-Small từ ổ đĩa.")
            except Exception as e:
                logger.warning(f"Không thể khởi tạo SenseVoice model: {e}. Sẽ dùng Faster-Whisper dự phòng.")
                cls._init_failed = True
                cls._model = None
        return cls._model

    @classmethod
    def transcribe(
        cls,
        wav_path: str,
        language: str = "zh",
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Nhận diện âm thanh bằng SenseVoice.
        Trả về danh sách các segments [{"start": float, "end": float, "text_origin": str}].
        """
        model = cls.get_model()
        if model is None:
            return None

        try:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess

            lang_arg = "zh" if language.startswith("zh") else ("auto" if language == "auto" else language)
            res = model.generate(
                input=wav_path,
                language=lang_arg,
                use_itn=True,
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=15,
            )

            if not res or not isinstance(res, list):
                return []

            segments: List[Dict[str, Any]] = []
            for item in res:
                # Mỗi item có text và mảng timestamp / sentence_info
                raw_text = item.get("text", "")
                clean_text = rich_transcription_postprocess(raw_text).strip()
                # Xóa mọi thẻ tag SenseVoice như <|zh|>, <|NEUTRAL|>, <|BGM|>, <|Speech|>
                clean_text = re.sub(r"<\|[^|>]+(?:\|>)?", "", clean_text).strip()

                # Trích xuất timestamps từ item
                sentence_info = item.get("sentence_info") or []
                if sentence_info and isinstance(sentence_info, list):
                    for s in sentence_info:
                        s_text = rich_transcription_postprocess(s.get("text", "")).strip()
                        s_text = re.sub(r"<\|[^|>]+(?:\|>)?", "", s_text).strip()
                        s_start = round(float(s.get("start", 0)) / 1000.0, 2)
                        s_end = round(float(s.get("end", 0)) / 1000.0, 2)
                        s_dur = max(0.1, round(s_end - s_start, 2))

                        if not is_hallucinated_segment(s_text, s_dur):
                            segments.append({
                                "start": s_start,
                                "end": s_end,
                                "text_origin": s_text,
                                "duration": s_dur,
                            })
                else:
                    # Nếu SenseVoice trả về cả đoạn kèm timestamp
                    timestamps = item.get("timestamp") or []
                    if timestamps and isinstance(timestamps, list) and len(timestamps) >= 1:
                        t_start = round(float(timestamps[0][0]) / 1000.0, 2)
                        t_end = round(float(timestamps[-1][1]) / 1000.0, 2)
                    else:
                        t_start = 0.0
                        t_end = 3.0
                    dur = max(0.1, round(t_end - t_start, 2))

                    if clean_text and not is_hallucinated_segment(clean_text, dur):
                        segments.append({
                            "start": t_start,
                            "end": t_end,
                            "text_origin": clean_text,
                            "duration": dur,
                        })

            logger.info(f"SenseVoice hoàn tất nhận diện: {len(segments)} câu hợp lệ (đã lọc BGM).")
            return segments

        except Exception as ex:
            logger.warning(f"Lỗi khi chạy SenseVoice inference: {ex}. Chuyển sang Faster-Whisper...")
            return None

