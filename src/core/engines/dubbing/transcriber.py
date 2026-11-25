import os
import re
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
try:
    import torch  # type: ignore
    from faster_whisper import WhisperModel  # type: ignore
except ImportError:
    torch = None  # type: ignore
    WhisperModel = None  # type: ignore
from src.core.config import settings
from src.core.engines.dubbing.hallucination_filter import (
    is_hallucinated_segment,
    filter_repeated_hallucination_segments,
)
from src.core.engines.dubbing.multimodal_fusion import MultimodalFusionEngine

logger = logging.getLogger("dubbing_transcriber")


class DubbingTranscriber:
    """Engine bóc tách giọng nói phụ đề bằng SenseVoice-Small & Faster-Whisper chống ảo giác BGM."""

    _model_cache: Dict[str, WhisperModel] = {}

    @classmethod
    def get_model(cls, model_size: str = "base") -> WhisperModel:
        """Tải hoặc lấy model Faster-Whisper đã được cache trong RAM/GPU."""
        if model_size not in cls._model_cache:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            whisper_cache_dir = settings.HF_CACHE_DIR / "whisper"
            whisper_cache_dir.mkdir(parents=True, exist_ok=True)

            model_target = model_size
            # Ưu tiên load snapshot offline có sẵn trong ổ đĩa để triệt tiêu độ trễ mạng
            snap_dir = whisper_cache_dir / f"models--Systran--faster-whisper-{model_size}" / "snapshots"
            if snap_dir.exists():
                snaps = [p for p in snap_dir.iterdir() if p.is_dir()]
                if snaps:
                    model_target = str(snaps[0])

            logger.info(f"Đang nạp mô hình Faster-Whisper '{model_size}' trên {device} ({compute_type})...")
            cls._model_cache[model_size] = WhisperModel(
                model_size_or_path=model_target,
                device=device,
                compute_type=compute_type,
                download_root=str(whisper_cache_dir),
            )
        return cls._model_cache[model_size]

    @classmethod
    def extract_audio_from_video(cls, video_path: str, output_wav: Optional[str] = None) -> str:
        """Trích xuất âm thanh từ video sang định dạng WAV 16kHz Mono kèm bộ lọc tăng cường giọng nói."""
        if not output_wav:
            output_wav = str(settings.TEMP_DIR / f"temp_{Path(video_path).stem}.wav")

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-af", "highpass=f=100,lowpass=f=6500,dynaudnorm",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_wav,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err_text = res.stderr.decode("utf-8", errors="ignore")
            if "does not contain any stream" in err_text or "Output file is empty" in err_text:
                logger.warning(f"Video không có track âm thanh hợp lệ: {video_path}")
                return ""
            raise RuntimeError(f"Lỗi khi trích xuất âm thanh: {err_text}")

        return output_wav

    @classmethod
    def _split_segment_by_sentences(cls, seg: Any) -> List[Dict[str, Any]]:
        """
        Kỹ thuật VideoLingo Step 3.2: Tách câu theo ngữ nghĩa (Semantic & Clause Splitting).
        - Ngắt tại ranh giới dấu câu hoặc liên từ ngữ pháp (nhưng, vì, cho nên, thế mà...).
        - Đảm bảo mỗi dòng phụ đề luôn đạt chuẩn Netflix: 4 đến 14 chữ, súc tích, trọn vẹn ý nghĩa.
        """
        words = getattr(seg, "words", None) or []
        dur = float(seg.end - seg.start)
        txt = seg.text.strip()
        if not txt or re.fullmatch(r"^[\d\.\s\-\:\,\[\]\(\)\<\>\|\/，。！？、；：“”‘’（）~～\•\*\_]+$", txt):
            return []

        # Câu ngắn dưới 3.5s và dưới 14 chữ: Giữ nguyên để người đọc không bị ngắt vụn
        if not words or (dur <= 3.5 and len(txt) <= 14):
            return [{"start": round(float(seg.start), 2), "end": round(float(seg.end), 2), "text_origin": txt}]

        sub_segs = []
        curr_words = []
        _CONJUNCTION_SPLIT = re.compile(r"(?:但是|因为|所以|如果|然后|而且|可是|然而|不过)")

        for w in words:
            curr_words.append(w)
            w_text = getattr(w, "word", "")
            is_major_punc = bool(re.search(r"[。！？!?；;\n]", w_text))
            is_comma = bool(re.search(r"[，,]", w_text))
            curr_dur = curr_words[-1].end - curr_words[0].start
            curr_txt = "".join([getattr(cw, "word", "") for cw in curr_words]).strip()
            curr_len = len(re.sub(r"[^\w]", "", curr_txt))

            # Điều kiện ngắt VideoLingo:
            # 1. Dấu câu chính (chấm, hỏi, than, chấm phẩy) sau ít nhất 1.0s
            # 2. Dấu phẩy khi câu đã đủ dài (>= 2.5s hoặc >= 8 chữ)
            # 3. Gặp liên từ khi câu đã >= 3.0s
            should_split = False
            if is_major_punc and curr_dur >= 1.0:
                should_split = True
            elif is_comma and (curr_dur >= 2.5 or curr_len >= 8):
                should_split = True
            elif _CONJUNCTION_SPLIT.search(w_text) and curr_dur >= 3.0 and curr_len >= 8:
                should_split = True
            elif curr_dur >= 5.5 or curr_len >= 18:
                should_split = True

            if should_split:
                joined = "".join([getattr(cw, "word", "") for cw in curr_words]).strip()
                if joined and not re.fullmatch(r"^[\d\.\s\-\:\,\[\]\(\)\<\>\|\/，。！？、；：“”‘’（）~～\•\*\_]+$", joined):
                    sub_segs.append({
                        "start": round(float(curr_words[0].start), 2),
                        "end": round(float(curr_words[-1].end), 2),
                        "text_origin": joined,
                    })
                curr_words = []

        if curr_words:
            joined = "".join([getattr(cw, "word", "") for cw in curr_words]).strip()
            if joined and not re.fullmatch(r"^[\d\.\s\-\:\,\[\]\(\)\<\>\|\/，。！？、；：“”‘’（）~～\•\*\_]+$", joined):
                sub_segs.append({
                    "start": round(float(curr_words[0].start), 2),
                    "end": round(float(curr_words[-1].end), 2),
                    "text_origin": joined,
                })

        return sub_segs if sub_segs else [{"start": round(float(seg.start), 2), "end": round(float(seg.end), 2), "text_origin": txt}]

    @classmethod
    def _run_whisper_asr(
        cls,
        wav_path: str,
        language: str = "zh",
        model_size: str = "base",
        beam_size: int = 5,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Nhận diện giọng nói từ file WAV qua Faster-Whisper kèm bộ lọc ảo giác BGM."""
        if not wav_path or not os.path.exists(wav_path):
            return []

        model = cls.get_model(model_size)
        logger.info(f"Chạy Faster-Whisper ASR '{language}' (beam={beam_size}, word_timestamps=True)...")

        vad_params = dict(
            threshold=0.35, min_speech_duration_ms=250, max_speech_duration_s=7.0,
            min_silence_duration_ms=400, speech_pad_ms=250,
        )

        segments, info = model.transcribe(
            wav_path,
            language=language if language != "auto" else None,
            beam_size=max(1, beam_size),
            word_timestamps=True,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            vad_filter=True,
            vad_parameters=vad_params,
        )

        total_dur = float(info.duration) if info and info.duration else 0.0
        result: List[Dict[str, Any]] = []

        for seg in segments:
            no_speech = getattr(seg, "no_speech_prob", None)
            sub_items = cls._split_segment_by_sentences(seg)
            for item in sub_items:
                item_dur = round(float(item["end"] - item["start"]), 2)
                if is_hallucinated_segment(item["text_origin"], item_dur, no_speech_prob=no_speech):
                    continue
                item["id"] = len(result)
                item["duration"] = item_dur
                item["text_translated"] = ""
                result.append(item)

            if progress_callback and total_dur > 0:
                pct = min(100, int((seg.end / total_dur) * 100))
                progress_callback(int(seg.end), int(total_dur), pct)

        if not result:
            fb_segs, _ = model.transcribe(
                wav_path, language=language if language != "auto" else None,
                beam_size=max(1, beam_size), condition_on_previous_text=False,
                word_timestamps=True, vad_filter=False,
            )
            for seg in fb_segs:
                no_speech = getattr(seg, "no_speech_prob", None)
                sub_items = cls._split_segment_by_sentences(seg)
                for item in sub_items:
                    item_dur = round(float(item["end"] - item["start"]), 2)
                    if is_hallucinated_segment(item["text_origin"], item_dur, no_speech_prob=no_speech):
                        continue
                    item["id"] = len(result)
                    item["duration"] = item_dur
                    item["text_translated"] = ""
                    result.append(item)

        return filter_repeated_hallucination_segments(result)

    @classmethod
    def transcribe(
        cls,
        media_path: str,
        language: str = "zh",
        model_size: str = "base",
        beam_size: int = 5,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
        use_ocr: bool = True,
    ) -> List[Dict[str, Any]]:
        """Nhận diện lời thoại kết hợp Đa Phương Thức (Multi-Modal Fusion: OCR + ASR) chạy song song."""
        temp_wav = None
        try:
            is_video = media_path.lower().endswith((".mp4", ".mkv", ".mov", ".flv", ".webm", ".avi"))
            if is_video and (not os.path.exists(media_path) or os.path.getsize(media_path) < 10000):
                raise RuntimeError("File video tải về bị rỗng hoặc lỗi mạng. Vui lòng thử lại.")

            ocr_segs: List[Dict[str, Any]] = []
            asr_segs: List[Dict[str, Any]] = []

            if use_ocr and is_video:
                wav_path = cls.extract_audio_from_video(media_path)
                temp_wav = wav_path
                p_lock = Lock()
                p_state = {"ocr": 0, "asr": 0, "cur_s": 0, "tot_s": 0}

                def make_sub_cb(task_name: str):
                    def _cb(cur_s: int, tot_s: int, pct: int):
                        if not progress_callback:
                            return
                        with p_lock:
                            p_state[task_name] = pct
                            p_state["cur_s"] = max(p_state["cur_s"], cur_s)
                            if tot_s > p_state["tot_s"]:
                                p_state["tot_s"] = tot_s
                            comb_pct = (p_state["ocr"] + p_state["asr"]) // 2
                            progress_callback(p_state["cur_s"], p_state["tot_s"], comb_pct)
                    return _cb

                def _ocr_worker():
                    try:
                        from src.core.engines.dubbing.video_ocr_engine import VideoOCREngine
                        return VideoOCREngine.extract_subtitles_from_video(
                            video_path=media_path,
                            sample_interval_sec=0.50,
                            progress_callback=make_sub_cb("ocr"),
                        )
                    except Exception as err:
                        logger.warning(f"Video OCR gặp sự cố ({err}), fallback sang ASR: {err}")
                        return []

                def _asr_worker():
                    # Đã có OCR gánh văn bản, Faster-Whisper dùng beam=2 để tăng tốc suy luận x2.5 lần
                    return cls._run_whisper_asr(
                        wav_path, language, model_size, min(beam_size, 2), make_sub_cb("asr")
                    )

                logger.info("Khởi chạy song song Video OCR và Faster-Whisper ASR (Dual-Stream)...")
                with ThreadPoolExecutor(max_workers=2) as pool:
                    f_ocr = pool.submit(_ocr_worker)
                    f_asr = pool.submit(_asr_worker)
                    ocr_segs = f_ocr.result()
                    asr_segs = f_asr.result()
            else:
                wav_path = cls.extract_audio_from_video(media_path) if is_video else media_path
                temp_wav = wav_path if is_video else None
                asr_segs = cls._run_whisper_asr(wav_path, language, model_size, beam_size, progress_callback)

            # Dung hợp Đa Phương Thức (Multi-Modal Fusion)
            if ocr_segs and asr_segs:
                logger.info(f"Kích hoạt Multi-Modal Fusion: {len(ocr_segs)} OCR + {len(asr_segs)} ASR...")
                return MultimodalFusionEngine.fuse(ocr_segs, asr_segs)
            elif ocr_segs:
                return MultimodalFusionEngine.stitch_consecutive_ocr_fragments(ocr_segs)
            return asr_segs

        finally:
            if temp_wav and os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass
