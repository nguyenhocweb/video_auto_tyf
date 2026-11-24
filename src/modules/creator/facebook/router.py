import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form

from src.modules.creator.facebook.schemas import (
    FacebookPageItem,
    FacebookVideoItem,
    FacebookPostItem,
    AvailableVideoItem,
    PublishReelRequest,
    PublishReelResponse,
    TokenStatusResponse,
    UpdateTokenRequest,
)
from src.modules.creator.facebook.service import FacebookService

logger = logging.getLogger("facebook_router")

router = APIRouter(prefix="/facebook", tags=["Creator - Facebook Pages & Reels"])


@router.get("/token-status", response_model=TokenStatusResponse)
async def get_token_status():
    """Kiểm tra trạng thái User Access Token (hợp lệ hay đã hết hạn)."""
    try:
        return await FacebookService.get_token_status()
    except Exception as ex:
        logger.error(f"Lỗi kiểm tra token status: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/token")
async def update_facebook_token(req: UpdateTokenRequest):
    """Cập nhật User Token mới, tự động đổi lấy Long-Lived Token (60 ngày) và nạp toàn bộ Pages."""
    try:
        return await FacebookService.update_user_token(req)
    except Exception as ex:
        logger.error(f"Lỗi cập nhật Facebook Token: {ex}")
        raise HTTPException(status_code=400, detail=str(ex))


@router.get("/pages", response_model=List[FacebookPageItem])
async def get_managed_pages(
    force_refresh: bool = Query(False, description="Làm mới trực tiếp từ Meta Graph API")
):
    """Lấy danh sách tất cả các Trang Facebook (mặc định lấy từ Cache MongoDB để mở siêu tốc)."""
    try:
        return await FacebookService.get_pages(force_refresh=force_refresh)
    except Exception as ex:
        logger.error(f"Lỗi khi lấy danh sách Facebook Pages: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/pages/{page_id}/videos", response_model=List[FacebookVideoItem])
async def get_page_videos(
    page_id: str,
    limit: int = Query(25, ge=1, le=100, description="Số lượng video cần lấy"),
    force_refresh: bool = Query(False, description="Làm mới video trực tiếp từ Meta"),
):
    """Lấy danh sách video/Reels của Fanpage (Ưu tiên Cache MongoDB hiển thị tức thì)."""
    try:
        return await FacebookService.get_page_videos(
            page_id=page_id, limit=limit, force_refresh=force_refresh
        )
    except Exception as ex:
        logger.error(f"Lỗi lấy video của page [{page_id}]: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/pages/{page_id}/posts", response_model=List[FacebookPostItem])
async def get_page_posts(
    page_id: str,
    limit: int = Query(25, ge=1, le=100, description="Số lượng bài viết cần lấy"),
    force_refresh: bool = Query(False, description="Làm mới bài viết trực tiếp từ Meta"),
):
    """Lấy danh sách bài viết trên Fanpage (Ưu tiên Cache MongoDB)."""
    try:
        return await FacebookService.get_page_posts(
            page_id=page_id, limit=limit, force_refresh=force_refresh
        )
    except Exception as ex:
        logger.error(f"Lỗi lấy bài viết của page [{page_id}]: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/available-videos", response_model=List[AvailableVideoItem])
async def get_available_rendered_videos():
    """Lấy danh sách các video đã làm sạch / Dubbing trên server để đăng Reels 1-Click."""
    try:
        return FacebookService.get_available_rendered_videos()
    except Exception as ex:
        logger.error(f"Lỗi lấy danh sách video sẵn có: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/publish-reel", response_model=PublishReelResponse)
async def publish_reel(req: PublishReelRequest):
    """Đăng video có sẵn trên máy chủ lên Facebook Reels."""
    try:
        return await FacebookService.publish_reel(req)
    except Exception as ex:
        logger.error(f"Lỗi xuất bản Facebook Reel: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/upload-and-publish-reel", response_model=PublishReelResponse)
async def upload_and_publish_reel(
    file: UploadFile = File(..., description="File video MP4"),
    caption: str = Form("", description="Tiêu đề và nội dung Reel"),
    page_id: Optional[str] = Form(None, description="Page ID đích"),
):
    """Tải file video trực tiếp từ máy lên và đăng lên Facebook Reels."""
    try:
        if not file.filename.lower().endswith((".mp4", ".mov")):
            raise HTTPException(status_code=400, detail="Chỉ hỗ trợ định dạng video .mp4 hoặc .mov")
        contents = await file.read()
        return await FacebookService.upload_and_publish_reel(
            file_bytes=contents,
            filename=file.filename,
            caption=caption,
            page_id=page_id,
        )
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Lỗi upload và xuất bản Reel: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


facebook_router = router
