import os
import re
import shutil
import asyncio
import logging
import subprocess
import unicodedata
import urllib.parse
import urllib.request
import json
from typing import List, Optional

from src.core.engines.dubbing.qwen_translator import QwenInProcessTranslator

logger = logging.getLogger("executor_helpers")


class ExecutorHelpers:
    @staticmethod
    def remove_vietnamese_accents(text: str) -> str:
        """Chuyển đổi chuỗi tiếng Việt có dấu thành không dấu chuẩn xác."""
        normalized = unicodedata.normalize("NFD", text)
        no_accent = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        no_accent = no_accent.replace("đ", "d").replace("Đ", "D")
        return no_accent

    @staticmethod
    def clean_douyin_title(raw_text: str) -> str:
        """Xóa sạch hoàn toàn các hashtag #... và @mention tiếng Trung gốc khỏi tiêu đề Douyin."""
        if not raw_text:
            return ""
        text = re.sub(r"#[^\s#]+", " ", raw_text)
        text = re.sub(r"@[^\s@]+", " ", text)
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    async def translate_to_vietnamese(cls, text: str) -> str:
        """Dịch chuẩn xác sang tiếng Việt và đảm bảo tuyệt đối không còn chữ Hán."""
        cleaned = cls.clean_douyin_title(text)
        if not cleaned or re.match(r"^Video\s*\d+$", cleaned, flags=re.IGNORECASE):
            return ""

        # 1. Ưu tiên dịch tiêu đề bằng LLM điện ảnh (Gemini / Qwen)
        try:
            from src.core.utils.text_sanitizer import clean_subtitle_text, is_ai_boilerplate
            llm_title = await asyncio.to_thread(
                QwenInProcessTranslator.translate_single_line, cleaned, 3.0
            )
            if llm_title and not re.search(r"[\u4e00-\u9fff]", llm_title):
                clean_title = clean_subtitle_text(llm_title)
                if clean_title and not is_ai_boilerplate(clean_title):
                    return clean_title.strip()
        except Exception as e_llm:
            logger.debug(f"LLM title translation error: {e_llm}")

        translated = ""
        # 2. Dự phòng qua REST API nếu LLM tạm thời chưa khả dụng
        try:
            encoded = urllib.parse.quote(cleaned)
            api_url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=vi&dt=t&q={encoded}"
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )

            def _fetch_gtx():
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return "".join([item[0] for item in data[0] if item and item[0]])

            translated = await asyncio.to_thread(_fetch_gtx)
        except Exception as e1:
            logger.debug(f"Direct translate error: {e1}")

        # 3. Xóa triệt để mọi chữ Hán và ghi chú boilerplate còn sót lại
        if translated:
            from src.core.utils.text_sanitizer import clean_subtitle_text
            translated = clean_subtitle_text(translated)
        if re.search(r"[\u4e00-\u9fff]", translated):
            translated = re.sub(r"[\u4e00-\u9fff]", "", translated).strip()

        if not translated or len(translated) < 3 or re.match(r"^Video\s*\d+$", translated, flags=re.IGNORECASE):
            return ""

        return translated.strip()

    @classmethod
    def generate_hashtags(
        cls,
        title: str,
        config_hashtags: Optional[str] = None,
        auto_add_title_tag: bool = True,
    ) -> str:
        """Tự động sinh bộ hashtags từ tên video tiếng Việt và cấu hình người dùng."""
        tags: List[str] = []

        # Không tạo hashtag từ title nếu video gốc không có tên hoặc title dạng "Video 123456"
        if (
            auto_add_title_tag
            and title
            and not re.search(r"[\u4e00-\u9fff]", title)
            and not re.match(r"^Video\s*\d+$", title, flags=re.IGNORECASE)
        ):
            clean_title = re.sub(r"[^\w\s]", " ", title)
            no_accent = cls.remove_vietnamese_accents(clean_title)
            words = [w.capitalize() for w in no_accent.split() if w.isalnum()]
            if words:
                full_tag = f"#{''.join(words[:5])}"
                tags.append(full_tag)

        if config_hashtags:
            custom_tags = [t.strip() for t in config_hashtags.split() if t.strip()]
            for ct in custom_tags:
                if re.search(r"[\u4e00-\u9fff]", ct):
                    continue
                tag_formatted = ct if ct.startswith("#") else f"#{ct}"
                if tag_formatted not in tags:
                    tags.append(tag_formatted)

        return " ".join(tags)

    @staticmethod
    def download_stream_to_file(video_stream_url: str, output_path: str) -> None:
        """Tải file video từ CDN Douyin về ổ đĩa với User-Agent chuẩn."""
        req = urllib.request.Request(
            video_stream_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.douyin.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=90) as resp, open(output_path, "wb") as out:
            shutil.copyfileobj(resp, out)

    @classmethod
    async def render_dubbed_video_for_automation(
        cls,
        local_video_path: str,
        campaign: dict,
        item_id: str,
        music_url: Optional[str] = None,
    ) -> str:
        """Thực thi pipeline Vietsub/Thuyết minh hoàn chỉnh cho video automation."""
        from src.core.engines.dubbing.transcriber import DubbingTranscriber
        from src.core.engines.dubbing.translator import DubbingTranslator
        from src.core.engines.dubbing.audio_aligner import DubbingAudioAligner
        from src.core.engines.dubbing.video_mixer import DubbingVideoMixer
        from src.core.engines.dubbing.subtitle_remover import SubtitleRemover
        from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository
        from src.core.config import settings

        mode = campaign.get("processing_mode", "vietsub")
        temp_dir = settings.TEMP_DIR / f"auto_dub_{item_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Kiểm tra track âm thanh; nếu thiếu do DASH stream thì mux music_url vào
        has_audio = False
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", local_video_path],
                capture_output=True, text=True, check=False
            )
            has_audio = "audio" in probe.stdout.lower()
        except Exception:
            pass

        if not has_audio and music_url:
            raw_audio = str(temp_dir / f"music_{item_id}.mp3")
            muxed_vid = str(temp_dir / f"muxed_{item_id}.mp4")
            try:
                await asyncio.to_thread(cls.download_stream_to_file, music_url, raw_audio)
                mux_res = await asyncio.to_thread(
                    lambda: subprocess.run(["ffmpeg", "-y", "-i", local_video_path, "-i", raw_audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", muxed_vid], capture_output=True, check=False)
                )
                if mux_res.returncode == 0 and os.path.exists(muxed_vid):
                    local_video_path = muxed_vid
            except Exception as e:
                logger.warning(f"Không thể mux audio trong automation: {e}")

        try:
            # 1. Nhận diện giọng nói kết hợp Video OCR bóc tách phụ đề gốc trên khung hình (Multi-Modal Fusion)
            use_ocr = bool(campaign.get("use_ocr", True))
            segments_raw = await asyncio.to_thread(
                DubbingTranscriber.transcribe,
                media_path=local_video_path,
                language="zh",
                model_size=getattr(settings, "WHISPER_MODEL_SIZE", "base"),
                use_ocr=use_ocr,
            )
            if not segments_raw:
                logger.warning(f"Whisper/OCR không nhận diện được đoạn thoại nào cho {item_id}, dùng video gốc.")
                return local_video_path

            # 2. Dịch qua Groq / Gemini Pool
            from src.modules.creator.dubbing.groq_keys_repository import GroqKeysMongoRepository
            groq_repo, gemini_repo = GroqKeysMongoRepository(), GeminiKeysMongoRepository()
            act_groq, act_gemini = await groq_repo.get_active_keys(), await gemini_repo.get_active_keys()

            translated_segments = await asyncio.to_thread(
                DubbingTranslator.translate_segments,
                segments=segments_raw,
                source_lang="zh-CN",
                target_lang="vi",
                groq_keys=act_groq,
                gemini_keys=act_gemini,
            )

            # 2.1. Cổng kiểm soát chất lượng tự động (Automated QA Gate) & Điều phối nhịp độ phụ đề
            from src.core.engines.dubbing.qa_gate import AutomatedQAGate
            from src.core.engines.dubbing.subtitle_pacer import SubtitlePacer
            translated_segments, qa_rep = AutomatedQAGate.audit_and_clean_subtitles(translated_segments)
            logger.info(f"Automation item {item_id} QA Score: {qa_rep['score']}/10 (Approved: {qa_rep['is_approved']})")
            translated_segments = SubtitlePacer.pace_segments(translated_segments)

            # Nhận diện vùng phụ đề gốc để che mờ ôm khít và căn chữ đè chuẩn 100%
            ymin_r, ymax_r, opt_margin_v = await asyncio.to_thread(
                SubtitleRemover.detect_subtitle_region, local_video_path, translated_segments
            )
            ass_path = str(temp_dir / f"sub_{item_id}.ass")
            DubbingTranslator.export_ass(
                translated_segments,
                ass_path,
                font_size=int(campaign.get("font_size", 31)),
                use_translated=True,
                margin_v=opt_margin_v,
            )

            # 3. Soft blur che phụ đề gốc theo timeline
            video_for_mix = local_video_path
            if campaign.get("remove_subtitles", True):
                cleaned_path = str(temp_dir / f"clean_{item_id}.mp4")
                await asyncio.to_thread(
                    SubtitleRemover.clean_video,
                    input_video_path=local_video_path,
                    output_video_path=cleaned_path,
                    segments=translated_segments,
                    ymin_ratio=ymin_r,
                    ymax_ratio=ymax_r,
                )
                video_for_mix = cleaned_path

            # 4. Tạo audio thuyết minh nếu mode == "dubbing" hoặc "both"
            dubbed_audio_path = None
            if mode in ["dubbing", "both"]:
                total_dur = float(translated_segments[-1]["end"]) if translated_segments else 30.0
                dubbed_audio_path = str(temp_dir / f"dubbed_{item_id}.wav")
                voice_src = campaign.get("voice_source", "preset")
                voice_pid = campaign.get("voice_profile_id") if voice_src == "profile" else None
                voice_preset = campaign.get("voice_preset", "vi-VN-NamMinhNeural")

                await DubbingAudioAligner.build_dubbing_track(
                    segments=translated_segments,
                    total_duration_sec=total_dur,
                    output_track_path=dubbed_audio_path,
                    voice=voice_preset,
                    voice_profile_id=voice_pid,
                )

            # 5. Render hoàn chỉnh
            rendered_mp4 = str(settings.DUBBING_OUTPUT_DIR / f"auto_final_{item_id}.mp4")
            await asyncio.to_thread(
                DubbingVideoMixer.mix_video,
                video_path=video_for_mix,
                output_path=rendered_mp4,
                mode=mode,
                subtitle_path=ass_path,
                dubbed_audio_path=dubbed_audio_path,
                bgm_volume=0.08,
                voice_volume=1.35,
            )
            return rendered_mp4

        except Exception as e:
            logger.error(f"Lỗi pipeline lồng tiếng/vietsub cho video {item_id}: {e}", exc_info=True)
            return local_video_path

