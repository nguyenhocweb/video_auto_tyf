import os
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from src.core.config import settings
from src.core.engines.stitch.video_stitcher import VideoStitcher
from src.core.engines.douyin.extractor import DouyinExtractor
from src.modules.creator.automation.hook_pool_repo import HookPoolMongoRepository
from src.modules.creator.automation.executor_helpers import ExecutorHelpers
from src.modules.creator.bgm.service import BgmService
from src.modules.shared.cloudinary.service import FastCloudinaryService
from src.modules.creator.stitch.schemas import (
    ManualStitchRequest,
    ManualStitchResponse,
    HookItemResponse,
    HookListResponse,
)

logger = logging.getLogger("stitch_service")


class StitchService:
    def __init__(self, hook_repo: Optional[HookPoolMongoRepository] = None):
        self.hook_repo = hook_repo or HookPoolMongoRepository()
        self.bgm_service = BgmService()

    @staticmethod
    async def _resolve_source_to_local_file(source: str, temp_dir: Path, prefix: str) -> str:
        """Nếu source là link web Douyin/TikTok -> bóc tách và tải; nếu là file local -> dùng luôn."""
        s = source.strip()
        if os.path.exists(s):
            return s

        if s.startswith("http://") or s.startswith("https://"):
            logger.info(f"Đang bóc tách video từ đường dẫn web: {s}")
            info = await DouyinExtractor.extract_no_watermark_video(s)
            stream_url = info.get("video_url")
            if not stream_url:
                raise ValueError(f"Không thể bóc tách luồng MP4 sạch từ link: {s}")

            local_path = str(temp_dir / f"{prefix}_{uuid.uuid4().hex[:6]}.mp4")
            await asyncio.to_thread(ExecutorHelpers.download_stream_to_file, stream_url, local_path)
            if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
                raise ValueError(f"Tải video từ CDN thất bại: {s}")
            return local_path

        raise FileNotFoundError(f"Nguồn video không hợp lệ (không phải link web hoặc file tồn tại): {s}")

    async def manual_stitch(self, req: ManualStitchRequest, user_id: str) -> ManualStitchResponse:
        """Thực hiện ghép nối 2 video thủ công theo yêu cầu."""
        temp_dir = settings.TEMP_DIR / "manual_stitch"
        temp_dir.mkdir(parents=True, exist_ok=True)

        raw_hook_path = await self._resolve_source_to_local_file(req.hook_source, temp_dir, "raw_hook")
        raw_body_path = await self._resolve_source_to_local_file(req.body_source, temp_dir, "raw_body")

        clipped_hook_path = str(temp_dir / f"hook_clip_{uuid.uuid4().hex[:6]}.mp4")
        out_filename = f"stitch_{uuid.uuid4().hex[:8]}.mp4"
        out_stitched_path = str(temp_dir / out_filename)

        bgm_path = None
        if req.audio_mode == "bgm_override":
            chosen_bgm_id = None
            if req.bgm_ids and len(req.bgm_ids) > 0:
                import random
                chosen_bgm_id = random.choice(req.bgm_ids)
                logger.info(f"Đã random chọn bài BGM '{chosen_bgm_id}' từ danh sách {len(req.bgm_ids)} bài")
            elif req.bgm_id:
                chosen_bgm_id = req.bgm_id

            if chosen_bgm_id:
                track = await self.bgm_service.get_bgm_by_id(chosen_bgm_id)
                if track:
                    file_path = track.get("file_path")
                    if file_path and isinstance(file_path, str) and os.path.exists(file_path):
                        bgm_path = file_path
                    elif file_path:
                        cand = settings.BGM_STORAGE_DIR / Path(file_path).name
                        if cand.exists():
                            bgm_path = str(cand)

        try:
            # 1. Cắt đoạn Hook chuẩn hóa theo aspect_ratio (9:16 hoặc 16:9)
            logger.info(f"Cắt Hook ({req.hook_duration}s, {req.aspect_ratio})...")
            await asyncio.to_thread(
                VideoStitcher.extract_hook_clip,
                raw_video_path=raw_hook_path,
                duration=req.hook_duration,
                out_path=clipped_hook_path,
                aspect_ratio=req.aspect_ratio,
            )

            # 2. Ghép nối Hook + Body với hiệu ứng mờ dần xfade
            logger.info(f"Tiến hành ghép nối (Bỏ {req.body_skip_start}s đầu, {req.aspect_ratio}, trans={req.transition_duration}s)...")
            await asyncio.to_thread(
                VideoStitcher.stitch_hook_and_body,
                hook_path=clipped_hook_path,
                body_path=raw_body_path,
                body_skip_sec=req.body_skip_start,
                out_path=out_stitched_path,
                audio_mode=req.audio_mode,
                bgm_path=bgm_path,
                aspect_ratio=req.aspect_ratio,
                transition_duration=req.transition_duration,
            )

            final_dur = VideoStitcher.get_media_duration(out_stitched_path)
            preview_url = f"/api/v1/creator/stitch/stream/{out_filename}"
            final_video_path = out_stitched_path

            # Bắt buộc upload video thành phẩm lên Cloudinary để lưu trữ CDN & giải phóng ổ cứng VPS
            cloud_res = await FastCloudinaryService.upload_large_file(
                file_path=out_stitched_path,
                filename=out_filename,
                folder="video_ai/stitched_videos",
                resource_type="video",
            )
            if cloud_res and cloud_res.get("secure_url"):
                preview_url = cloud_res["secure_url"]
                final_video_path = cloud_res["secure_url"]
                if os.path.exists(out_stitched_path):
                    try:
                        os.remove(out_stitched_path)
                    except Exception:
                        pass

            return ManualStitchResponse(
                success=True,
                video_path=final_video_path,
                filename=out_filename,
                preview_url=preview_url,
                duration=round(final_dur, 2),
                hook_duration=req.hook_duration,
                body_skip_sec=req.body_skip_start,
                audio_mode=req.audio_mode,
                aspect_ratio=req.aspect_ratio,
                transition_duration=req.transition_duration,
                message=f"Ghép nối video 2 nguồn thành công (chuyển cảnh chậm {req.transition_duration}s)!",
            )
        finally:
            # Dọn dẹp clip hook tạm sau khi đã ghép
            if os.path.exists(clipped_hook_path):
                try:
                    os.remove(clipped_hook_path)
                except Exception:
                    pass

    async def get_hooks(self, campaign_id: Optional[str] = None) -> HookListResponse:
        """Lấy danh sách các đoạn Hook trong kho đệm."""
        query = {}
        if campaign_id:
            query["campaign_id"] = campaign_id

        cursor = self.hook_repo.col.find(query).sort("created_at", -1).limit(100)
        items: List[HookItemResponse] = []
        available_cnt = 0
        used_cnt = 0

        async for doc in cursor:
            st = doc.get("status", "available")
            if st == "available":
                available_cnt += 1
            else:
                used_cnt += 1

            items.append(
                HookItemResponse(
                    id=str(doc.get("id") or doc.get("_id")),
                    campaign_id=str(doc.get("campaign_id", "")),
                    item_id=str(doc.get("item_id", "")),
                    video_url=doc.get("video_url", ""),
                    title=doc.get("title", ""),
                    hook_path=doc.get("hook_path", ""),
                    duration=float(doc.get("duration", 0.0)),
                    status=st,
                    used_count=int(doc.get("used_count", 0)),
                    created_at=str(doc.get("created_at", "")),
                )
            )

        return HookListResponse(
            total=len(items),
            available_count=available_cnt,
            used_count=used_cnt,
            hooks=items,
        )

    async def delete_hook(self, hook_id: str) -> bool:
        """Xóa một Hook khỏi kho đệm và dọn dẹp file vật lý."""
        doc = await self.hook_repo.col.find_one({"id": hook_id})
        if not doc:
            return False

        hook_path = doc.get("hook_path")
        if hook_path and os.path.exists(hook_path):
            try:
                os.remove(hook_path)
            except Exception as ex:
                logger.warning(f"Không thể xóa file {hook_path}: {ex}")

        res = await self.hook_repo.col.delete_one({"id": hook_id})
        return res.deleted_count > 0

    @staticmethod
    def get_or_create_test_samples() -> Dict[str, Any]:
        """Tạo hoặc lấy 2 video mẫu chuẩn 1080x1920 có âm thanh để người dùng bấm test nhanh."""
        import subprocess
        sample_dir = settings.TEMP_DIR / "stitch_samples"
        sample_dir.mkdir(parents=True, exist_ok=True)
        hook_path = sample_dir / "sample_hook_test.mp4"
        body_path = sample_dir / "sample_body_test.mp4"

        if not hook_path.exists() or hook_path.stat().st_size == 0:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=6:size=1080x1920:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=800:duration=6",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                str(hook_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=15)

        if not body_path.exists() or body_path.stat().st_size == 0:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc2=duration=12:size=1080x1920:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                str(body_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=15)

        return {
            "success": True,
            "hook_sample": str(hook_path),
            "body_sample": str(body_path),
            "hook_title": "Video Mẫu 1 (Test Hook 6s)",
            "body_title": "Video Mẫu 2 (Test Body 12s)",
        }
