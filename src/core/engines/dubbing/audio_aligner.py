import os
import re
import uuid
import random
import asyncio
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydub import AudioSegment
import edge_tts
from src.core.config import settings
from src.core.utils.text_sanitizer import clean_subtitle_text

logger = logging.getLogger("dubbing_audio_aligner")


class DubbingAudioAligner:
    """Engine co giãn tốc độ giọng đọc thuyết minh và ghép timeline chính xác, chống lồng tiếng tuyệt đối."""

    DEFAULT_VOICE = "vi-VN-NamMinhNeural"

    @classmethod
    def clean_text_for_tts(cls, text: str) -> str:
        """Làm sạch văn bản đầu vào cho TTS, loại bỏ emoji, tag xưng hô và ký tự lạ gây drop audio."""
        if not text:
            return ""
        clean = clean_subtitle_text(text)
        clean = re.sub(r"[\u4e00-\u9fff]+", "", clean)
        _num_map = {"0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn", "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín", "10": "mười"}
        clean = re.sub(r"\b(\d{1,2})\b", lambda m: _num_map.get(m.group(1), m.group(1)), clean)
        for pat, repl in [(r"\bJS\b", "cương thi"), (r"\bWeChat\b", "tin nhắn"), (r"\bDouyin\b", "mạng xã hội"), (r"\bvcl\b", "quá"), (r"\bvãi\b", "thật sự")]:
            clean = re.sub(pat, repl, clean, flags=re.IGNORECASE)
        clean = re.sub(r"([A-Za-zÀ-ỹ\s]{3,20}),\s*\1", r"\1", clean)
        clean = re.sub(r"[^\w\s\.,!\?\'\"\-\–]", " ", clean, flags=re.UNICODE)
        clean = re.sub(r"[\,\;\:\-\–\~]+$", ".", clean).strip()
        clean = re.sub(r"\s+", " ", clean).strip()
        return f"{clean}..." if clean and len(re.sub(r"[^\w]", "", clean)) <= 2 else clean

    @classmethod
    def strip_audio_silence(cls, seg: AudioSegment, silence_thresh: float = -42.0) -> AudioSegment:
        """Cắt bỏ khoảng lặng đầu (leading silence) để giọng đọc phát ra tức thì ngay khi chữ xuất hiện."""
        if len(seg) < 120:
            return seg
        start_trim, end_trim, chunk_len = 0, len(seg), 10
        while start_trim < min(len(seg) - 50, 400) and seg[start_trim : start_trim + chunk_len].dBFS < silence_thresh:
            start_trim += chunk_len
        while end_trim > start_trim + 50 and seg[end_trim - chunk_len : end_trim].dBFS < silence_thresh:
            end_trim -= chunk_len
        trimmed = seg[start_trim : min(len(seg), end_trim + 80)]
        return trimmed if len(trimmed) >= 80 else seg

    @classmethod
    def optimize_text_for_pace(cls, text: str, available_dur_sec: float) -> str:
        """Tối ưu câu thoại súc tích chuẩn điện ảnh khớp với thời lượng phát âm (~3.5 từ/giây)."""
        if not text or available_dur_sec <= 0:
            return text
        words = text.split()
        if len(words) <= max(3, int(available_dur_sec * 3.5)):
            return text
        condensed = text
        replacements = [
            (r"\bở tại nơi này\b", "tại đây"), (r"\bngay tại thời điểm này\b", "lúc này"),
            (r"\btại thời điểm hiện tại\b", "bây giờ"), (r"\bchẳng phải là .*? hay sao\b", "chẳng phải sao"),
            (r"\bchính là vì lý do\b", "bởi vì"), (r"\bthực sự là rất\b", "rất"),
            (r"\bhoàn toàn không có\b", "không có"), (r"\bkhông thể nào mà\b", "không thể"),
            (r"\bcho dù là như thế nào\b", "dù thế nào"), (r"\bkhông cần phải lo lắng\b", "đừng lo"),
            (r"\bđợi cho đến khi\b", "chờ khi"), (r"\bsau khi chúng ăn chúng ta\b", "khi chúng ăn"),
            (r"\bnăng lượng và sức mạnh\b", "sức mạnh"), (r"\bthay đổi thành hình dạng\b", "biến thành"),
            (r"\btrở thành con người\b", "thành người"), (r"\bchúng ta đã không ăn\b", "ta chưa ăn"),
            (r"\btiêu thụ quả cay\b", "ăn quả"), (r"\btiêu thụ\b", "ăn"), (r"\btôi cũng không hiểu\b", "tôi không hiểu"),
            (r"\bnhất định phải\b", "phải"), (r"^(thực ra thì|thế nhưng mà|bởi vì là|nói tóm lại là)\s+", ""),
        ]
        for pattern, repl in replacements:
            condensed = re.sub(pattern, repl, condensed, flags=re.IGNORECASE).strip()
        return re.sub(r"\s+", " ", condensed).strip()

    @classmethod
    async def synthesize_single_segment_tts(
        cls,
        text: str,
        output_path: str,
        voice: str = "vi-VN-NamMinhNeural",
        voice_profile_id: Optional[str] = None,
        rate: Optional[str] = "+8%",
    ) -> str:
        """Sinh âm thanh giọng đọc Edge-TTS với tốc độ nhanh nhẹn (+8%), dứt khoát chuẩn điện ảnh."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cleaned_text = cls.clean_text_for_tts(text)

        if not cleaned_text or not re.search(r"[\w\u00C0-\u1EF9]", cleaned_text):
            AudioSegment.silent(duration=300, frame_rate=24000).export(output_path, format="wav")
            return output_path

        clean_voice = voice if voice and "Neural" in voice else cls.DEFAULT_VOICE
        dot_clean = re.sub(r"[\,\;\:\-\–\.\!\?…]+$", "", cleaned_text) + "."
        simplified = re.sub(r"[^\w\s\u00C0-\u1EF9]", " ", cleaned_text).strip() + "."

        # BẢO TOÀN GIỌNG NÓI 100%: Tuyệt đối KHÔNG tráo giọng khác giới tính (alt_voice) khi gặp lỗi.
        # Tất cả các lần thử lại (retries) bắt buộc giữ nguyên 1 giọng duy nhất đã chọn.
        strategies = [
            (clean_voice, rate if rate else "+0%", cleaned_text, 0.15),
            (clean_voice, "+0%", dot_clean, 0.35),
            (clean_voice, "+0%", simplified, 0.60),
            (clean_voice, "+0%", f"{cleaned_text[:60]}...", 0.90),
        ]

        for s_idx, (v_name, v_rate, s_text, sleep_s) in enumerate(strategies):
            try:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                communicate = edge_tts.Communicate(s_text, v_name, rate=v_rate)
                await communicate.save(output_path)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 300:
                    return output_path
            except Exception as err:
                logger.warning(f"Edge-TTS '{v_name}' lần {s_idx + 1}/4 ({err}) với '{s_text[:25]}'")
                await asyncio.sleep(sleep_s + random.uniform(0.05, 0.10))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        AudioSegment.silent(duration=500, frame_rate=24000).export(output_path, format="wav")
        return output_path

    @classmethod
    def fit_audio_to_duration(
        cls, input_audio_path: str, output_audio_path: str, target_duration_sec: float, min_speed: float = 1.0, max_speed: float = 1.35
    ) -> str:
        """Co giãn tốc độ giọng đọc mượt mà (min 1.0x bình thường -> max 1.35x), không làm chậm giọng."""
        seg = AudioSegment.from_file(input_audio_path)
        current_dur_sec = len(seg) / 1000.0
        target_duration_sec = target_duration_sec if target_duration_sec > 0 else current_dur_sec
        speed_factor = current_dur_sec / target_duration_sec
        if speed_factor <= 1.0 or (0.98 <= speed_factor <= 1.02):
            seg.export(output_audio_path, format="wav")
            return output_audio_path

        speed_factor = max(min_speed, min(speed_factor, max_speed))
        cmd = ["ffmpeg", "-y", "-i", input_audio_path, "-filter:a", f"atempo={speed_factor:.3f}", "-ar", "24000", "-vn", output_audio_path]
        if subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
            seg.export(output_audio_path, format="wav")
        return output_audio_path

    @classmethod
    async def build_dubbing_track(
        cls,
        segments: List[Dict[str, Any]],
        total_duration_sec: float,
        output_track_path: str,
        voice: str = "vi-VN-NamMinhNeural",
        voice_profile_id: Optional[str] = None,
    ) -> str:
        """Ghép timeline lồng tiếng tuần tự: Hỗ trợ cả giọng Training/Clone lẫn Neural, triệt tiêu lồng tiếng."""
        temp_dir = settings.TEMP_DIR / f"dub_temp_{uuid.uuid4().hex[:10]}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        trained_model, trained_prompt = None, None
        if voice_profile_id and str(voice_profile_id).strip() not in ["", "none", "null"]:
            try:
                from src.modules.shared.voice.service import OmniVoiceService
                from src.modules.shared.voice import profile_synthesizer
                omni_service = OmniVoiceService()
                trained_model = omni_service.get_model()
                trained_prompt = await profile_synthesizer.resolve_voice_prompt(trained_model, str(voice_profile_id))
                logger.info(f"Đã nạp sẵn profile giọng training vào RAM: {voice_profile_id}")
            except Exception as exc:
                logger.warning(f"Không thể nạp trước giọng training ({exc}), sẽ fallback về Edge-TTS: {voice}")
                trained_model, trained_prompt = None, None

        try:
            total_ms = int(total_duration_sec * 1000)
            master_track = AudioSegment.silent(duration=total_ms, frame_rate=24000)
            last_end_ms = 0

            # Xử lý tuần tự từng đoạn một (Sequential Chunking), xong đoạn này mới sang đoạn sau
            for i, seg in enumerate(segments):
                text = seg.get("text_translated", "").strip()
                text = re.sub(r"[\u4e00-\u9fff]", "", text).strip()
                if not text or re.fullmatch(r"^[\d\.\s\-\:\,\[\]\(\)\<\>\|\/，。！？、；：“”‘’（）~～\•\*\_]+$", text):
                    continue

                seg_id, start_sec, end_sec = seg.get("id", i), float(seg["start"]), float(seg["end"])
                base_dur = max(0.9, end_sec - start_sec)
                target_start_ms = int(start_sec * 1000)

                # NGUYÊN TẮC VÀNG CHỐNG LỒNG TIẾNG (ZERO-COLLISION PLAYHEAD):
                # 1 người thuyết minh không bao giờ nói đè lên chính mình.
                # Bắt buộc bắt đầu sau khi câu trước đã dứt ít nhất 60ms.
                actual_start_ms = max(target_start_ms, last_end_ms + 60)

                if i + 1 < len(segments):
                    next_target_start_ms = int(float(segments[i + 1]["start"]) * 1000)
                    gap_to_next_sec = max(0.6, (next_target_start_ms - actual_start_ms) / 1000.0)
                    available_dur = max(0.8, min(base_dur + 1.2, gap_to_next_sec))
                else:
                    available_dur = base_dur + 1.5

                text_to_speak = cls.optimize_text_for_pace(text, available_dur)
                word_count = len(text_to_speak.split())
                est_sec = word_count / 3.2

                rate_str = "+0%"
                if est_sec > available_dur * 1.25:
                    rate_str = "+14%"
                elif est_sec > available_dur * 1.10:
                    rate_str = "+10%"
                elif est_sec > available_dur:
                    rate_str = "+6%"

                raw_seg_wav = str(temp_dir / f"raw_{seg_id}.wav")
                fitted_seg_wav = str(temp_dir / f"fit_{seg_id}.wav")

                # Bước 1: Ưu tiên tạo bằng giọng Training nếu đã nạp (tuần tự, timeout 12s chống treo)
                is_trained_ok = False
                if trained_model and trained_prompt:
                    try:
                        from src.modules.shared.voice import profile_synthesizer
                        is_trained_ok = await asyncio.wait_for(
                            profile_synthesizer.synthesize_segment_local(
                                model=trained_model,
                                prompt=trained_prompt,
                                text=text_to_speak,
                                output_path=raw_seg_wav,
                                speed=1.0,
                                num_step=16,
                                gender="MALE" if "NamMinh" in voice else "FEMALE",
                            ),
                            timeout=12.0,
                        )
                    except Exception as err:
                        logger.warning(f"Lỗi giọng training câu {i + 1} ({err}), tự động fallback Edge-TTS")
                        is_trained_ok = False

                # Bước 2: Fallback 4 cấp sang Edge-TTS nếu không có giọng training hoặc lỗi
                if not is_trained_ok or not os.path.exists(raw_seg_wav) or os.path.getsize(raw_seg_wav) < 300:
                    await cls.synthesize_single_segment_tts(
                        text=text_to_speak, output_path=raw_seg_wav, voice=voice, rate=rate_str
                    )

                cls.fit_audio_to_duration(
                    input_audio_path=raw_seg_wav, output_audio_path=fitted_seg_wav, target_duration_sec=available_dur, max_speed=1.35
                )

                if os.path.exists(fitted_seg_wav):
                    spoken_seg = cls.strip_audio_silence(AudioSegment.from_file(fitted_seg_wav))

                    # CẮT ĐUÔI AN TOÀN TUYỆT ĐỐI (ZERO OVERLAP GUARANTEE):
                    if i + 1 < len(segments):
                        next_target_start_ms = int(float(segments[i + 1]["start"]) * 1000)
                        max_window_ms = next_target_start_ms - actual_start_ms - 50
                        if max_window_ms > 350 and len(spoken_seg) > max_window_ms:
                            spoken_seg = spoken_seg[:max_window_ms].fade_out(40)
                        elif max_window_ms <= 350 and len(spoken_seg) > max(300, max_window_ms + 80):
                            spoken_seg = spoken_seg[:max(300, max_window_ms + 80)].fade_out(40)

                    actual_end_ms = actual_start_ms + len(spoken_seg)
                    if actual_end_ms > len(master_track):
                        master_track += AudioSegment.silent(duration=(actual_end_ms - len(master_track) + 1000), frame_rate=24000)

                    master_track = master_track.overlay(spoken_seg, position=actual_start_ms)
                    last_end_ms = actual_end_ms

                # Dọn dẹp RAM / CUDA VRAM định kỳ mỗi 10 câu
                if (i + 1) % 10 == 0:
                    import gc
                    gc.collect()
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass

                await asyncio.sleep(0.12)

            if trained_prompt and voice_profile_id:
                try:
                    from src.modules.shared.voice.repository_mongo import VoiceMongoRepository
                    await VoiceMongoRepository().increment_profile_usage(str(voice_profile_id))
                except Exception:
                    pass

            Path(output_track_path).parent.mkdir(parents=True, exist_ok=True)
            master_track.export(output_track_path, format="wav")
            return output_track_path

        finally:
            import shutil
            import gc
            shutil.rmtree(temp_dir, ignore_errors=True)
            gc.collect()
