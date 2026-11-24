import os
import uuid
import shutil
import asyncio
import logging
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from src.core.config import settings
from src.core.engines.dubbing.transcriber import DubbingTranscriber
from src.core.engines.dubbing.translator import DubbingTranslator
from src.core.engines.dubbing.audio_aligner import DubbingAudioAligner
from src.core.engines.dubbing.video_mixer import DubbingVideoMixer
from src.core.engines.dubbing.subtitle_remover import SubtitleRemover
from src.modules.creator.dubbing.schemas import (
    DubbingTranscribeRequest,
    DubbingTranscribeResponse,
    DubbingTranslateRequest,
    DubbingTranslateResponse,
    DubbingRenderRequest,
    AutoDubbingFromUrlRequest,
    DubbingCleanVideoRequest,
    DubbingJobResponse,
    SubtitleSegmentSchema,
)
from src.modules.creator.dubbing.repository import DubbingMongoRepository
from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository
from src.modules.shared.cloudinary.service import FastCloudinaryService

logger = logging.getLogger("dubbing_service")


class DubbingService:
    """Service điều phối toàn bộ chu trình xử lý Vietsub & Dubbing Thuyết Minh đa chế độ."""

    def __init__(self, repo: Optional[DubbingMongoRepository] = None):
        self.repo = repo or DubbingMongoRepository()
        settings.DUBBING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _ensure_local_media(url_or_path: str, temp_dir: Path) -> str:
        """Đảm bảo media nằm trên ổ đĩa local. Nếu là URL thì tải về temp_dir."""
        if os.path.exists(url_or_path):
            return url_or_path

        temp_name = f"download_{uuid.uuid4().hex[:8]}.mp4"
        local_path = str(temp_dir / temp_name)
        req = urllib.request.Request(
            url_or_path,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp, open(local_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        return local_path

    async def enqueue_auto_dubbing_from_url(
        self, payload: AutoDubbingFromUrlRequest, user_id: str
    ) -> DubbingJobResponse:
        """Đưa yêu cầu Vietsub & Thuyết Minh tự động từ URL vào hàng đợi chạy ngầm."""
        from src.modules.creator.dubbing.dubbing_queue_manager import DubbingQueueManager

        job = await self.repo.create_job({
            "user_id": user_id,
            "video_url": payload.url,
            "source_url": payload.url,
            "title": "Đang phân tích link...",
            "mode": payload.mode,
            "voice_source": payload.voice_source,
            "voice_preset": payload.voice_preset,
            "voice_profile_id": payload.voice_profile_id,
            "voice_name": payload.voice_name,
            "remove_subtitles": payload.remove_subtitles,
            "status": "pending",
            "progress_step": "Đang chờ vào hàng đợi...",
            "progress_percent": 0,
        })
        queue_mgr = DubbingQueueManager.get_instance()
        await queue_mgr.enqueue_auto_dubbing_task(job["id"], user_id, payload.model_dump())
        return DubbingJobResponse(**job)

    async def delete_job(self, job_id: str, user_id: str) -> bool:
        """Xóa tác vụ thuộc quyền sở hữu của người dùng."""
        return await self.repo.delete_job(job_id, user_id)

    async def retry_job(self, job_id: str, user_id: str) -> Optional[DubbingJobResponse]:
        """Thử lại tác vụ vietsub / dubbing theo job_id."""
        from src.modules.creator.dubbing.dubbing_queue_manager import DubbingQueueManager

        queue_mgr = DubbingQueueManager.get_instance()
        job = await queue_mgr.retry_job(job_id, user_id)
        return DubbingJobResponse(**job) if job else None

    async def transcribe_video(self, payload: DubbingTranscribeRequest) -> DubbingTranscribeResponse:
        """Nhận diện lời thoại video gốc bằng Faster-Whisper."""
        temp_dir = settings.TEMP_DIR / f"transcribe_{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            local_video = await asyncio.to_thread(self._ensure_local_media, payload.video_url, temp_dir)
            segments_raw = await asyncio.to_thread(
                DubbingTranscriber.transcribe,
                media_path=local_video,
                language=payload.language,
                model_size=payload.model_size,
            )
            segments = [SubtitleSegmentSchema(**seg) for seg in segments_raw]
            total_duration = segments[-1].end if segments else 0.0
            return DubbingTranscribeResponse(
                video_url=payload.video_url,
                total_segments=len(segments),
                duration_total=total_duration,
                segments=segments,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def translate_segments(self, payload: DubbingTranslateRequest) -> DubbingTranslateResponse:
        """Dịch nội dung các đoạn phụ đề sang tiếng Việt."""
        raw_list = [s.model_dump() for s in payload.segments]
        keys_repo = GeminiKeysMongoRepository()
        active_keys = await keys_repo.get_active_keys()
        updated_raw = await asyncio.to_thread(
            DubbingTranslator.translate_segments,
            segments=raw_list,
            source_lang=payload.source_lang,
            target_lang=payload.target_lang,
            gemini_keys=active_keys,
        )
        return DubbingTranslateResponse(segments=[SubtitleSegmentSchema(**s) for s in updated_raw])

    async def clean_video_subtitles(self, payload: DubbingCleanVideoRequest, user_id: str) -> DubbingJobResponse:
        """Xóa sạch phụ đề cứng gốc khỏi video bằng AI Inpainting độc lập."""
        job = await self.repo.create_job({
            "user_id": user_id,
            "video_url": payload.video_url,
            "mode": "clean_subtitles",
        })
        job_id = job["id"]
        temp_dir = settings.TEMP_DIR / f"clean_{job_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            local_video = await asyncio.to_thread(self._ensure_local_media, payload.video_url, temp_dir)
            output_cleaned = str(settings.DUBBING_OUTPUT_DIR / f"cleaned_{job_id}.mp4")
            await asyncio.to_thread(
                SubtitleRemover.clean_video,
                input_video_path=local_video,
                output_video_path=output_cleaned,
                ymin_ratio=payload.ymin_ratio,
                ymax_ratio=payload.ymax_ratio,
            )
            video_url = f"/api/v1/creator/dubbing/download/cleaned_{job_id}.mp4"
            await self.repo.update_progress(job_id=job_id, status="completed", progress_step="Hoàn thành", progress_percent=100, output_video_url=video_url)
            return DubbingJobResponse(id=job_id, user_id=user_id, mode="clean_subtitles", status="completed", output_video_url=video_url, created_at=job.get("created_at", ""))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def render_dubbing_job(self, payload: DubbingRenderRequest, user_id: str) -> DubbingJobResponse:
        """Thực hiện render hoàn chỉnh theo 3 chế độ (vietsub, dubbing, both)."""
        job = await self.repo.create_job({
            "user_id": user_id,
            "video_url": payload.video_url,
            "mode": payload.mode,
            "voice_source": payload.voice_source,
            "voice_preset": payload.voice_preset,
            "voice_profile_id": payload.voice_profile_id,
            "segments": [s.model_dump() for s in payload.segments],
        })
        job_id = job["id"]
        try:
            res_video_url, srt_url, ass_url = await self._process_render_pipeline(job_id, payload)
            await self.repo.update_progress(
                job_id=job_id, status="completed", progress_step="Hoàn thành", progress_percent=100, output_video_url=res_video_url, subtitle_srt_url=srt_url, subtitle_ass_url=ass_url
            )
            return DubbingJobResponse(
                id=job_id, user_id=user_id, mode=payload.mode, status="completed", output_video_url=res_video_url, subtitle_srt_url=srt_url, subtitle_ass_url=ass_url, created_at=job.get("created_at", "")
            )
        except Exception as exc:
            err_msg = str(exc)
            await self.repo.update_progress(job_id=job_id, status="failed", progress_step=f"Lỗi: {err_msg}", progress_percent=0, error_message=err_msg)
            return DubbingJobResponse(id=job_id, user_id=user_id, mode=payload.mode, status="failed", error_message=err_msg, created_at=job.get("created_at", ""))

    async def _process_render_pipeline(
        self, job_id: str, payload: DubbingRenderRequest
    ) -> Tuple[str, str, str]:
        """Pipeline con thực hiện chi tiết các bước xuất file phụ đề, lồng tiếng và mix video."""
        temp_dir = settings.TEMP_DIR / f"render_{job_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            local_video = await asyncio.to_thread(self._ensure_local_media, payload.video_url, temp_dir)
            segments_data = [s.model_dump() for s in payload.segments]
            source_video_for_mix = local_video
            ymin_r, ymax_r, opt_margin_v = await asyncio.to_thread(
                SubtitleRemover.detect_subtitle_region, local_video, segments_data
            )
            if payload.remove_subtitles:
                cleaned_video_path = str(temp_dir / f"cleaned_{job_id}.mp4")
                await asyncio.to_thread(
                    SubtitleRemover.clean_video,
                    input_video_path=local_video,
                    output_video_path=cleaned_video_path,
                    segments=segments_data,
                    ymin_ratio=ymin_r,
                    ymax_ratio=ymax_r,
                )
                source_video_for_mix = cleaned_video_path

            srt_path = str(settings.DUBBING_OUTPUT_DIR / f"sub_{job_id}.srt")
            ass_path = str(settings.DUBBING_OUTPUT_DIR / f"sub_{job_id}.ass")
            DubbingTranslator.export_srt(segments_data, srt_path, use_translated=True)
            sub_font_size = int(getattr(payload, "font_size", 31) or 31)
            DubbingTranslator.export_ass(
                segments_data, ass_path, font_size=sub_font_size, use_translated=True, margin_v=opt_margin_v
            )

            dubbed_audio_path = None
            if payload.mode in ["dubbing", "both"]:
                total_dur = segments_data[-1]["end"] if segments_data else 30.0
                dubbed_audio_path = str(temp_dir / f"dubbed_{job_id}.wav")
                await DubbingAudioAligner.build_dubbing_track(
                    segments=segments_data,
                    total_duration_sec=total_dur,
                    output_track_path=dubbed_audio_path,
                    voice=payload.voice_preset,
                    voice_profile_id=payload.voice_profile_id if payload.voice_source == "profile" else None,
                )

            rendered_video_path = str(settings.DUBBING_OUTPUT_DIR / f"rendered_{job_id}.mp4")
            await asyncio.to_thread(
                DubbingVideoMixer.mix_video,
                video_path=source_video_for_mix,
                output_path=rendered_video_path,
                mode=payload.mode,
                subtitle_path=ass_path,
                dubbed_audio_path=dubbed_audio_path,
                bgm_volume=payload.bgm_volume,
                voice_volume=payload.voice_volume,
            )

            video_url = f"/api/v1/creator/dubbing/download/rendered_{job_id}.mp4"
            try:
                c_res = await FastCloudinaryService.upload_large_file(
                    rendered_video_path, filename=f"dubbed_{job_id}.mp4", folder="video_ai/dubbed_videos", resource_type="video"
                )
                if c_res and c_res.get("secure_url"):
                    video_url = c_res["secure_url"]
            except Exception as c_exc:
                logger.warning(f"Upload Cloudinary video thất bại: {c_exc}")

            return video_url, f"/api/v1/creator/dubbing/download/sub_{job_id}.srt", f"/api/v1/creator/dubbing/download/sub_{job_id}.ass"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
