import os
import shutil
import urllib.request
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from src.core.config import settings
from src.modules.shared.ws.notification_ws import notify_user
from src.modules.shared.cloudinary.service import FastCloudinaryService
from src.core.engines.dubbing.video_mixer import DubbingVideoMixer
from src.modules.creator.bgm.service import BgmService
from src.modules.creator.dubbing.dubbing_notifier import DubbingNotifier

logger = logging.getLogger("dubbing_reup_helper")


class DubbingReupHelper:
    """Helper xử lý Mô hình 2: Lách bản quyền thuật toán (pHash, metadata) & ghép BGM sạch."""

    @classmethod
    async def process_reup_or_download(
        cls,
        job_id: str,
        user_id: str,
        local_video: str,
        title: str,
        cover_url: Optional[str],
        payload_data: Dict[str, Any],
        repo: Any,
        temp_dir: Path,
    ) -> None:
        mode = payload_data.get("mode", "download_only")
        # Kích hoạt mô hình 2 nếu mode là reup_transform hoặc có cờ anti_copyright=True
        is_reup = (mode == "reup_transform") or bool(payload_data.get("anti_copyright", True))

        if not is_reup:
            # Chế độ tải thuần túy không xử lý
            c_res = await FastCloudinaryService.upload_large_file(
                local_video, filename=f"video_{job_id}.mp4", folder="video_ai/downloaded_videos"
            )
            c_url = c_res.get("secure_url") if c_res else None
            out_url = c_url or f"/api/v1/creator/dubbing/download/orig_{job_id}.mp4"
            await repo.update_progress(
                job_id=job_id, status="completed", progress_step="Hoàn thành tải video sạch logo!",
                progress_percent=100, cloudinary_url=c_url, output_video_url=out_url,
            )
            await notify_user(user_id, "DUBBING_COMPLETED", {"job_id": job_id, "status": "completed", "percent": 100, "video_url": out_url})
            return

        # BẮT ĐẦU MÔ HÌNH 2: LÁCH THUẬT TOÁN & BẢN QUYỀN CHUẨN PRO
        await repo.update_progress(
            job_id=job_id, status="processing",
            progress_step="Mô hình 2: Đang biến đổi pHash, tẩy metadata & chọn BGM bản quyền sạch...",
            progress_percent=50,
        )
        await notify_user(user_id, "DUBBING_PROGRESS", {"job_id": job_id, "step": "Đang biến đổi lách thuật toán & mix BGM...", "percent": 50})

        # 1. Chọn BGM ngẫu nhiên từ kho nhạc theo Mood hoặc ID chỉ định (tự tải từ Cloudinary về cache)
        bgm_service = BgmService()
        req_mood = payload_data.get("bgm_mood")
        preferred_bgm_id = payload_data.get("bgm_id")
        _, bgm_local_path = await bgm_service.pick_and_resolve_random_bgm(
            user_id=user_id, mood=req_mood, preferred_id=preferred_bgm_id
        )

        # 2. Thực thi biến đổi video bằng FFmpeg (Zoom 1.04x, Crop, Color shift, BGM mix, Strip metadata)
        transformed_output = str(settings.DUBBING_OUTPUT_DIR / f"final_{job_id}.mp4")
        DubbingVideoMixer.transform_reup_video(
            video_path=local_video,
            output_path=transformed_output,
            bgm_path=bgm_local_path,
            bgm_volume=float(payload_data.get("bgm_volume", 0.90)),
            orig_audio_volume=float(payload_data.get("orig_audio_volume", 0.15)),
            zoom_factor=1.04,
        )

        # 3. Tải video thành phẩm lên Cloudinary CDN
        await repo.update_progress(
            job_id=job_id, status="processing", progress_step="Đang tải video thành phẩm lên CDN...", progress_percent=90
        )
        c_res = await FastCloudinaryService.upload_large_file(
            transformed_output, filename=f"final_{job_id}.mp4", folder="video_ai/reup_videos", resource_type="video"
        )
        c_url = c_res.get("secure_url") if c_res else None
        final_video_url = str(c_url) if c_url else f"/api/v1/creator/dubbing/download/final_{job_id}.mp4"

        # 4. Cập nhật hoàn thành 100%
        await repo.update_progress(
            job_id=job_id, status="completed",
            progress_step="Hoàn thành xuất sắc: Đã lách thuật toán pHash & ghép BGM sạch 100%!",
            progress_percent=100, output_video_url=final_video_url, cloudinary_url=c_url,
        )
        await notify_user(user_id, "DUBBING_COMPLETED", {"job_id": job_id, "video_url": final_video_url, "status": "completed"})
        await DubbingNotifier.notify_completed(user_id, job_id, title, final_video_url, cover_url)
        logger.info(f"Re-up Transform Job {job_id} hoàn tất 100%!")

