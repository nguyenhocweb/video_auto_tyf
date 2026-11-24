import os
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.responses import FileResponse

from src.core.config import settings
from src.core.engines.stitch.video_stitcher import VideoStitcher
from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.stitch.schemas import (
    ManualStitchRequest,
    ManualStitchResponse,
    HookListResponse,
)
from src.modules.creator.stitch.service import StitchService

logger = logging.getLogger("stitch_router")

router = APIRouter(prefix="/creator/stitch", tags=["Creator - Video Stitch Studio"])
stitch_service = StitchService()


def _get_user_id(user) -> str:
    if isinstance(user, dict):
        return str(user.get("id") or user.get("_id") or "default_user")
    return str(getattr(user, "id", "default_user"))


@router.post("/manual", response_model=ManualStitchResponse)
async def manual_stitch(
    req: ManualStitchRequest,
    current_user=Depends(get_current_user),
):
    """Ghép nối 2 nguồn video (Hook + Body) theo thông số người dùng cài đặt."""
    try:
        user_id = _get_user_id(current_user)
        return await stitch_service.manual_stitch(req=req, user_id=user_id)
    except Exception as ex:
        logger.error(f"Lỗi ghép nối video: {ex}")
        raise HTTPException(status_code=400, detail=str(ex))


@router.get("/hooks", response_model=HookListResponse)
async def get_hooks(
    campaign_id: Optional[str] = Query(None, description="Lọc theo chiến dịch cụ thể"),
    current_user=Depends(get_current_user),
):
    """Lấy danh sách các đoạn Hook trong kho đệm."""
    try:
        return await stitch_service.get_hooks(campaign_id=campaign_id)
    except Exception as ex:
        logger.error(f"Lỗi lấy danh sách Hook: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.delete("/hooks/{hook_id}")
async def delete_hook(
    hook_id: str,
    current_user=Depends(get_current_user),
):
    """Xóa một Hook khỏi kho đệm."""
    try:
        success = await stitch_service.delete_hook(hook_id)
        if not success:
            raise HTTPException(status_code=404, detail="Không tìm thấy Hook để xóa")
        return {"success": True, "message": "Đã xóa Hook thành công!"}
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Lỗi xóa Hook: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/stream/{filename}")
async def stream_stitched_video(filename: str):
    """Phát video đã ghép để xem thử trực tiếp trên trình duyệt."""
    clean_name = os.path.basename(filename)
    file_path = settings.TEMP_DIR / "manual_stitch" / clean_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy video đã ghép.")
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=clean_name,
    )


@router.post("/upload")
async def upload_stitch_media(
    file: UploadFile = File(..., description="File video MP4/MOV để ghép nối"),
    current_user=Depends(get_current_user),
):
    """Tải lên video trực tiếp từ máy tính để test hoặc ghép nối."""
    try:
        temp_dir = settings.TEMP_DIR / "stitch_uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = f"upload_{uuid.uuid4().hex[:8]}_{file.filename}"
        file_path = str(temp_dir / filename)

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        dur = VideoStitcher.get_media_duration(file_path)
        size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)

        return {
            "success": True,
            "file_path": file_path,
            "filename": file.filename,
            "duration": round(dur, 2),
            "size_mb": size_mb,
        }
    except Exception as ex:
        logger.error(f"Lỗi upload file stitch: {ex}")
        raise HTTPException(status_code=400, detail=str(ex))


@router.get("/samples")
async def get_test_samples(
    current_user=Depends(get_current_user),
):
    """Lấy 2 video mẫu chuẩn để người dùng bấm test nhanh 1-Click."""
    try:
        return StitchService.get_or_create_test_samples()
    except Exception as ex:
        logger.error(f"Lỗi tạo video mẫu: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))
