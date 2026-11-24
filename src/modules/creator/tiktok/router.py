import logging
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.tiktok.schemas import (
    TikTokAuthUrlResponse,
    TikTokChannelListResponse,
    PublishTikTokRequest,
    PublishTikTokResponse,
    TikTokVideoListResponse,
)
from src.modules.creator.tiktok.service import TikTokService

logger = logging.getLogger("tiktok_router")

tiktok_router = APIRouter(prefix="/tiktok", tags=["Creator - TikTok Publisher"])
service = TikTokService()


def _get_user_id(user: Any) -> str:
    """Trích xuất User ID từ JWT token dict hoặc object."""
    if isinstance(user, dict):
        return str(user.get("id") or user.get("_id") or "")
    return str(getattr(user, "id", ""))


@tiktok_router.get("/auth-url", response_model=TikTokAuthUrlResponse)
async def get_auth_url(
    scope: Optional[str] = Query(None),
    fe_origin: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    """Lấy đường dẫn ủy quyền TikTok OAuth v2 để kết nối Kênh."""
    try:
        user_id = _get_user_id(current_user)
        origin = fe_origin or "https://nguyen-video.vercel.app"
        state = f"{user_id}___{origin}"
        url = service.get_auth_url(user_id=state, scope=scope)
        return TikTokAuthUrlResponse(auth_url=url)
    except Exception as ex:
        logger.error(f"Lỗi tạo link TikTok OAuth: {ex}")
        raise HTTPException(status_code=400, detail=str(ex))


@tiktok_router.get("/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """TikTok chuyển hướng về endpoint này sau khi người dùng cấp quyền."""
    user_id = "default_user"
    fe_origin = "https://nguyen-video.vercel.app"

    if state:
        if "___" in state:
            parts = state.split("___", 1)
            user_id = parts[0] or user_id
            fe_origin = parts[1] or fe_origin
        else:
            user_id = state

    fe_redirect = f"{fe_origin.rstrip('/')}/creator/tiktok"
    if error:
        logger.warning(f"TikTok OAuth từ chối: {error} - {error_description}")
        return RedirectResponse(f"{fe_redirect}?tiktok_error={error}")

    if not code:
        raise HTTPException(status_code=400, detail="Thiếu mã Authorization Code từ TikTok.")

    try:
        await service.handle_callback(code=code, user_id=user_id)
        return RedirectResponse(f"{fe_redirect}?tiktok_connected=true")
    except Exception as ex:
        logger.error(f"Lỗi callback TikTok: {ex}")
        return RedirectResponse(f"{fe_redirect}?tiktok_error={str(ex)}")


@tiktok_router.get("/channels", response_model=TikTokChannelListResponse)
async def get_channels(current_user=Depends(get_current_user)):
    """Lấy danh sách tất cả các Kênh TikTok đã liên kết của người dùng."""
    try:
        return await service.get_channels(user_id=_get_user_id(current_user))
    except Exception as ex:
        logger.error(f"Lỗi lấy danh sách kênh TikTok: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@tiktok_router.get("/channels/{channel_id}/videos", response_model=TikTokVideoListResponse)
async def get_channel_videos(
    channel_id: str,
    max_count: int = Query(20, ge=1, le=50),
    current_user=Depends(get_current_user),
):
    """Lấy danh sách video của một Kênh TikTok."""
    return await service.get_channel_videos(
        user_id=_get_user_id(current_user), channel_id=channel_id, max_count=max_count
    )


@tiktok_router.delete("/channels/{channel_id}")
async def disconnect_channel(channel_id: str, current_user=Depends(get_current_user)):
    """Hủy liên kết một Kênh TikTok."""
    success = await service.disconnect_channel(user_id=_get_user_id(current_user), channel_id=channel_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh hoặc hủy liên kết thất bại.")
    return {"status": "success", "message": "Đã hủy liên kết kênh TikTok thành công."}


@tiktok_router.post("/publish", response_model=PublishTikTokResponse)
async def publish_video(
    channel_id: str = Form(...),
    title: str = Form(...),
    privacy_level: str = Form("PUBLIC_TO_EVERYONE"),
    disable_duet: bool = Form(False),
    disable_comment: bool = Form(False),
    disable_stitch: bool = Form(False),
    video_cover_timestamp_ms: int = Form(1000),
    video_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user=Depends(get_current_user),
):
    """Xuất bản video trực tiếp lên Kênh TikTok (Direct Post)."""
    user_id = _get_user_id(current_user)
    video_bytes = None
    if file:
        video_bytes = await file.read()

    req = PublishTikTokRequest(
        channel_id=channel_id,
        video_url=video_url,
        title=title,
        privacy_level=privacy_level,
        disable_duet=disable_duet,
        disable_comment=disable_comment,
        disable_stitch=disable_stitch,
        video_cover_timestamp_ms=video_cover_timestamp_ms,
    )
    return await service.publish_video_direct(user_id=user_id, request=req, video_bytes=video_bytes)
