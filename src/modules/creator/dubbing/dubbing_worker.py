import os
import time
import shutil
import asyncio
import logging
import subprocess
from typing import Dict, Any, Optional
import urllib.request

from src.core.config import settings
from src.modules.shared.ws.notification_ws import notify_user
from src.modules.shared.cloudinary.service import FastCloudinaryService
from src.core.engines.douyin.extractor import DouyinExtractor
from src.core.engines.dubbing.transcriber import DubbingTranscriber
from src.core.engines.dubbing.translator import DubbingTranslator
from src.core.engines.dubbing.audio_aligner import DubbingAudioAligner
from src.core.engines.dubbing.video_mixer import DubbingVideoMixer
from src.core.engines.dubbing.subtitle_remover import SubtitleRemover
from src.modules.creator.dubbing.repository import DubbingMongoRepository
from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository
from src.modules.creator.dubbing.groq_keys_repository import GroqKeysMongoRepository
from src.modules.creator.dubbing.dubbing_notifier import DubbingNotifier

logger = logging.getLogger("dubbing_worker")


async def execute_dubbing_worker(
    job_id: str, user_id: str, payload_data: Dict[str, Any], repo: DubbingMongoRepository
) -> None:
    """Tiến trình Worker thực thi 8 bước xử lý video chạy ngầm."""
    temp_dir = settings.TEMP_DIR / f"auto_dub_{job_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    title: str = str(payload_data.get("title") or "Video Douyin")
    cover_url: Optional[str] = None
    music_url: Optional[str] = None
    final_video_url: str = f"/api/v1/creator/dubbing/download/final_{job_id}.mp4"

    try:
        # Bước 1: Bóc tách video Douyin không logo
        await repo.update_progress(
            job_id=job_id, status="processing", progress_step="Đang bóc tách video Douyin sạch 1080p...", progress_percent=15
        )
        await notify_user(user_id, "DUBBING_PROGRESS", {"job_id": job_id, "step": "Đang bóc tách video...", "percent": 15})

        raw_url = payload_data.get("url", "").strip()
        local_video = str(temp_dir / f"orig_{job_id}.mp4")
        clean_url: str = raw_url

        if "douyin.com" in raw_url or "iesdouyin.com" in raw_url:
            res = await DouyinExtractor.extract_no_watermark_video(raw_url)
            douyin_video_url = res.get("video_url")
            music_url = res.get("music_url")
            title = str(res.get("title", title))
            cover_url = res.get("cover_url")
            if not douyin_video_url:
                raise RuntimeError("Không thể bóc tách luồng video sạch từ Douyin.")
            clean_url = str(douyin_video_url)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        }
        for attempt in range(3):
            try:
                req = urllib.request.Request(clean_url, headers=headers)
                with urllib.request.urlopen(req, timeout=90) as resp, open(local_video, "wb") as f_out:
                    shutil.copyfileobj(resp, f_out)
                if os.path.exists(local_video) and os.path.getsize(local_video) > 50000:
                    break
            except Exception as dl_err:
                if attempt == 2:
                    raise RuntimeError(f"Tải video từ CDN thất bại: {dl_err}")
                await asyncio.sleep(2)

        if not os.path.exists(local_video) or os.path.getsize(local_video) < 50000:
            raise RuntimeError("File video tải về từ CDN bị rỗng hoặc lỗi mạng. Vui lòng bấm Thử Lại.")

        # Tự động ghép luồng âm thanh nếu Douyin tách riêng video và audio stream (DASH/MSE)
        chk_cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "csv=p=0", local_video]
        has_audio = bool(subprocess.run(chk_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip())
        if not has_audio and music_url:
            local_music = str(temp_dir / f"music_{job_id}.mp3")
            try:
                m_req = urllib.request.Request(music_url, headers=headers)
                with urllib.request.urlopen(m_req, timeout=60) as m_resp, open(local_music, "wb") as m_out:
                    shutil.copyfileobj(m_resp, m_out)
                if os.path.exists(local_music) and os.path.getsize(local_music) > 1000:
                    mux_vid = str(temp_dir / f"muxed_{job_id}.mp4")
                    mux_cmd = ["ffmpeg", "-y", "-i", local_video, "-i", local_music, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", mux_vid]
                    if subprocess.run(mux_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0:
                        local_video = mux_vid
                        has_audio = True
                        logger.info(f"Đã ghép thành công âm thanh vào video {job_id}!")
            except Exception as mux_err:
                logger.warning(f"Lỗi ghép audio phụ: {mux_err}")

        await repo.update_progress(
            job_id=job_id, status="processing", progress_step="Đã tải video gốc. Bắt đầu nhận diện âm thanh...", progress_percent=25, title=title, cover_url=cover_url
        )
        await notify_user(user_id, "DUBBING_PROGRESS", {"job_id": job_id, "step": "Đã tải video gốc. Bắt đầu nhận diện âm thanh...", "percent": 25, "status": "processing", "title": title, "cover_url": cover_url})

        mode = payload_data.get("mode", "both")
        if mode in ["download_only", "reup_transform"]:
            from src.modules.creator.dubbing.dubbing_reup_helper import DubbingReupHelper
            await DubbingReupHelper.process_reup_or_download(
                job_id=job_id, user_id=user_id, local_video=local_video, title=title,
                cover_url=cover_url, payload_data=payload_data, repo=repo, temp_dir=temp_dir,
            )
            return

        # Bước 2: Nhận diện lời thoại (Faster-Whisper)
        loop = asyncio.get_running_loop()
        last_whisper_pct = -1
        last_notify_ts = 0.0

        def notify_step(msg: str, pct: int, count: Optional[int] = None):
            asyncio.run_coroutine_threadsafe(
                repo.update_progress(job_id=job_id, status="processing", progress_step=msg, progress_percent=pct, segments_count=count),
                loop,
            )
            asyncio.run_coroutine_threadsafe(
                notify_user(user_id, "DUBBING_PROGRESS", {"job_id": job_id, "step": msg, "percent": pct, "status": "processing"}),
                loop,
            )

        def on_whisper_progress(cur_sec: int, total_sec: int, pct: int):
            nonlocal last_whisper_pct, last_notify_ts
            now = time.time()
            if pct - last_whisper_pct >= 3 or pct >= 100 or (now - last_notify_ts >= 2.0):
                last_whisper_pct = pct
                last_notify_ts = now
                notify_step(f"Đang bóc tách đa phương thức: {cur_sec}s / {total_sec}s ({pct}%)...", 25 + int(pct * 0.15))

        # Mặc định kích hoạt Đa Phương Thức (Video OCR chữ + ASR âm thanh) cho mọi video
        effective_use_ocr = payload_data.get("use_ocr") is not False
        notify_step("Đang bóc tách Đa Phương Thức (OCR chữ hình ảnh + ASR âm thanh)...", 25)

        segments_raw = await asyncio.to_thread(
            DubbingTranscriber.transcribe,
            media_path=local_video,
            language="zh",
            model_size=getattr(settings, "WHISPER_MODEL_SIZE", "base"),
            beam_size=5,
            progress_callback=on_whisper_progress,
            use_ocr=effective_use_ocr,
        )
        if not segments_raw:
            raise RuntimeError("Không trích xuất được phụ đề hoặc lời thoại nào trong video này.")

        # Bước 3: Dịch phụ đề sang tiếng Việt
        last_trans_pct = -1

        def on_trans_progress(done_cnt: int, total_cnt: int):
            nonlocal last_trans_pct
            pct = int((done_cnt / total_cnt) * 100) if total_cnt > 0 else 100
            if pct - last_trans_pct >= 10 or pct >= 100:
                last_trans_pct = pct
                notify_step(f"Đang dịch phụ đề: {done_cnt}/{total_cnt} câu ({pct}%)...", 40 + int(pct * 0.15), total_cnt)

        groq_repo, gemini_repo = GroqKeysMongoRepository(), GeminiKeysMongoRepository()
        act_groq, act_gemini = await groq_repo.get_active_keys(), await gemini_repo.get_active_keys()
        engine_lbl = "Groq LPU (Qwen 3.8 27B)" if act_groq else "Gemini Pool"
        notify_step(f"Đang dịch {len(segments_raw)} câu thoại sang tiếng Việt qua {engine_lbl}...", 40, len(segments_raw))

        def on_key_used(k_id: str, success: bool):
            target_repo = groq_repo if k_id.startswith("groq_") else gemini_repo
            asyncio.run_coroutine_threadsafe(target_repo.record_usage(k_id, success), loop)

        translated_segments = await asyncio.to_thread(
            DubbingTranslator.translate_segments,
            segments=segments_raw,
            source_lang="zh-CN",
            target_lang="vi",
            progress_callback=on_trans_progress,
            groq_keys=act_groq,
            gemini_keys=act_gemini,
            on_key_used=on_key_used,
        )

        # Bước 3.5: Kiểm soát chất lượng bản dịch tự động (Automated QA Gate)
        from src.core.engines.dubbing.qa_gate import AutomatedQAGate
        from src.core.engines.dubbing.subtitle_pacer import SubtitlePacer
        translated_segments, qa_report = AutomatedQAGate.audit_and_clean_subtitles(translated_segments)
        logger.info(f"Job {job_id} QA Score: {qa_report['score']}/10 (Approved: {qa_report['is_approved']})")
        translated_segments = SubtitlePacer.pace_segments(translated_segments)

        # Nhận diện vùng phụ đề gốc để che mờ ôm khít và căn chữ đè chuẩn 100%
        ymin_r, ymax_r, opt_margin_v = await asyncio.to_thread(
            SubtitleRemover.detect_subtitle_region, local_video, translated_segments
        )

        srt_path = str(settings.DUBBING_OUTPUT_DIR / f"sub_{job_id}.srt")
        ass_path = str(settings.DUBBING_OUTPUT_DIR / f"sub_{job_id}.ass")
        DubbingTranslator.export_srt(translated_segments, srt_path, use_translated=True)
        DubbingTranslator.export_ass(
            translated_segments,
            ass_path,
            font_size=int(payload_data.get("font_size", 31)),
            use_translated=True,
            margin_v=opt_margin_v,
        )

        # Bước 4: Che phụ đề cứng tiếng Trung bằng Soft Blur Strip chuẩn Reels (theo timeline)
        video_for_mix = local_video
        if payload_data.get("remove_subtitles", True):
            await repo.update_progress(
                job_id=job_id, status="processing", progress_step="Đang che mờ phụ đề gốc theo timeline câu thoại (Chuẩn Reels)...", progress_percent=65
            )
            await notify_user(user_id, "DUBBING_PROGRESS", {"job_id": job_id, "step": "Đang che mờ phụ đề gốc theo timeline câu thoại (Chuẩn Reels)...", "percent": 65, "status": "processing"})
            cleaned_path = str(temp_dir / f"clean_{job_id}.mp4")
            await asyncio.to_thread(
                SubtitleRemover.clean_video,
                input_video_path=local_video,
                output_video_path=cleaned_path,
                segments=translated_segments,
                ymin_ratio=ymin_r,
                ymax_ratio=ymax_r,
            )
            video_for_mix = cleaned_path

        # Bước 5: Sinh giọng thuyết minh tiếng Việt
        dubbed_audio_path: Optional[str] = None
        if mode in ["dubbing", "both"]:
            await repo.update_progress(
                job_id=job_id, status="processing", progress_step="Đang tạo giọng đọc thuyết minh tiếng Việt khớp timeline...", progress_percent=80
            )
            await notify_user(user_id, "DUBBING_PROGRESS", {"job_id": job_id, "step": "Đang tạo giọng đọc thuyết minh tiếng Việt khớp timeline...", "percent": 80, "status": "processing"})
            total_dur = float(translated_segments[-1]["end"]) if translated_segments else 30.0
            dubbed_audio_path = str(temp_dir / f"dubbed_{job_id}.wav")
            await DubbingAudioAligner.build_dubbing_track(
                segments=translated_segments,
                total_duration_sec=total_dur,
                output_track_path=dubbed_audio_path,
                voice=payload_data.get("voice_preset", "vi-VN-NamMinhNeural"),
                voice_profile_id=payload_data.get("voice_profile_id") if payload_data.get("voice_source") == "profile" else None,
            )

        # Bước 6: Render ghép video bằng FFmpeg
        await repo.update_progress(
            job_id=job_id, status="processing", progress_step="Đang render video thành phẩm & ghép phụ đề/âm thanh...", progress_percent=90
        )
        await notify_user(user_id, "DUBBING_PROGRESS", {"job_id": job_id, "step": "Đang render video thành phẩm & ghép phụ đề/âm thanh...", "percent": 90, "status": "processing"})
        rendered_mp4 = str(settings.DUBBING_OUTPUT_DIR / f"final_{job_id}.mp4")
        await asyncio.to_thread(
            DubbingVideoMixer.mix_video,
            video_path=video_for_mix,
            output_path=rendered_mp4,
            mode=mode,
            subtitle_path=ass_path,
            dubbed_audio_path=dubbed_audio_path,
            bgm_volume=float(payload_data.get("bgm_volume", 0.08)),
            voice_volume=float(payload_data.get("voice_volume", 1.35)),
        )

        # Bước 7: Tải lên Cloudinary CDN
        await repo.update_progress(
            job_id=job_id, status="processing", progress_step="Đang tải video thành phẩm lên Cloudinary CDN...", progress_percent=95
        )
        await notify_user(user_id, "DUBBING_PROGRESS", {"job_id": job_id, "step": "Đang tải video thành phẩm lên Cloudinary CDN...", "percent": 95, "status": "processing"})
        c_url: Optional[str] = None
        try:
            c_res = await FastCloudinaryService.upload_large_file(rendered_mp4, filename=f"final_{job_id}.mp4", folder="video_ai/dubbed_videos", resource_type="video")
            if c_res and c_res.get("secure_url"):
                c_url = str(c_res["secure_url"])
                final_video_url = c_url
        except Exception as c_err:
            logger.warning(f"Upload Cloudinary thất bại, dùng local link: {c_err}")

        # Bước 8: Hoàn thành 100%
        await repo.update_progress(
            job_id=job_id, status="completed", progress_step="Hoàn thành xuất sắc 100%!",
            progress_percent=100, output_video_url=final_video_url, cloudinary_url=c_url,
            subtitle_srt_url=f"/api/v1/creator/dubbing/download/sub_{job_id}.srt",
            subtitle_ass_url=f"/api/v1/creator/dubbing/download/sub_{job_id}.ass",
            segments=translated_segments, segments_count=len(translated_segments),
        )
        await notify_user(user_id, "DUBBING_COMPLETED", {"job_id": job_id, "video_url": final_video_url, "status": "completed"})
        await DubbingNotifier.notify_completed(user_id, job_id, title, final_video_url, cover_url)
        logger.info(f"Dubbing Job {job_id} hoàn tất 100%!")

    except Exception as exc:
        err_msg = str(exc)
        logger.error(f"Dubbing Job {job_id} thất bại: {err_msg}", exc_info=True)
        await repo.update_progress(
            job_id=job_id, status="failed", progress_step=f"Thất bại: {err_msg[:120]}", progress_percent=0, error_message=err_msg
        )
        await notify_user(user_id, "DUBBING_FAILED", {"job_id": job_id, "error": err_msg, "status": "failed"})
        await DubbingNotifier.notify_failed(user_id, job_id, err_msg, title)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

