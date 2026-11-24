import logging
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from src.core.config import settings
from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.youtube.schemas import (
    YouTubeAuthUrlResponse,
    YouTubeChannelResponse,
    YouTubeChannelListResponse,
    YouTubeVideoListResponse,
    AvailableVideoItem,
    PublishShortsRequest,
    PublishShortsResponse,
    DeleteYouTubeVideoResponse,
)
from src.modules.creator.youtube.service import YouTubeService

logger = logging.getLogger("youtube_router")

router = APIRouter(prefix="/youtube", tags=["Creator - YouTube Shorts"])
service = YouTubeService()


def _get_user_id(user: Any) -> str:
    """Trích xuất User ID an toàn từ dict MongoDB hoặc Object."""
    if isinstance(user, dict):
        return str(user.get("id") or user.get("_id") or "")
    return str(getattr(user, "id", ""))


@router.get("/auth-url", response_model=YouTubeAuthUrlResponse)
async def get_auth_url(
    fe_origin: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    """Lấy đường link ủy quyền Google OAuth 2.0 cho Kênh YouTube."""
    try:
        user_id = _get_user_id(current_user)
        origin = (fe_origin or getattr(settings, "FRONTEND_URL", "https://nguyen-video.vercel.app")).rstrip("/")
        state = f"{user_id}___{origin}"
        url = service.get_auth_url(user_id=state)
        return YouTubeAuthUrlResponse(auth_url=url)
    except Exception as ex:
        logger.error(f"Lỗi lấy auth url: {ex}")
        raise HTTPException(status_code=400, detail=str(ex))


@router.get("/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """Google chuyển hướng về endpoint này sau khi người dùng cấp quyền."""
    user_id = "default_user"
    fe_origin = getattr(settings, "FRONTEND_URL", "https://nguyen-video.vercel.app").rstrip("/")

    if state:
        if "___" in state:
            parts = state.split("___", 1)
            user_id = parts[0] or user_id
            fe_origin = (parts[1] or fe_origin).rstrip("/")
        else:
            user_id = state

    fe_redirect = f"{fe_origin}/creator/youtube"

    if error:
        logger.warning(f"Google OAuth từ chối cấp quyền: {error}")
        return RedirectResponse(f"{fe_redirect}?youtube_error=access_denied")

    if not code:
        raise HTTPException(status_code=400, detail="Thiếu mã Authorization Code.")

    try:
        await service.handle_callback(code=code, user_id=user_id)
        return RedirectResponse(f"{fe_redirect}?youtube_connected=true")
    except Exception as ex:
        logger.error(f"Lỗi callback OAuth YouTube: {ex}")
        return RedirectResponse(f"{fe_redirect}?youtube_error={str(ex)}")


@router.get("/channels", response_model=YouTubeChannelListResponse)
async def get_channels(current_user=Depends(get_current_user)):
    """Lấy danh sách tất cả các Kênh YouTube đã liên kết của người dùng."""
    try:
        return await service.get_channels(user_id=_get_user_id(current_user))
    except Exception as ex:
        logger.error(f"Lỗi lấy danh sách kênh YouTube: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/channels/{channel_id}/videos", response_model=YouTubeVideoListResponse)
async def get_channel_videos(
    channel_id: str, limit: int = 25, current_user=Depends(get_current_user)
):
    """Lấy danh sách video và Shorts của một Kênh YouTube cụ thể."""
    return await service.get_channel_videos(
        user_id=_get_user_id(current_user), channel_id=channel_id, limit=limit
    )


@router.get("/available-videos", response_model=List[AvailableVideoItem])
async def get_available_videos(current_user=Depends(get_current_user)):
    """Lấy danh sách video sẵn có trong máy chủ để đăng Shorts 1-Click."""
    return service.get_available_rendered_videos()


@router.get("/channel", response_model=YouTubeChannelResponse)
async def get_channel_status(current_user=Depends(get_current_user)):
    """Lấy trạng thái Kênh YouTube đầu tiên (Backward compatibility)."""
    try:
        return await service.get_channel_status(user_id=_get_user_id(current_user))
    except Exception as ex:
        logger.error(f"Lỗi lấy trạng thái kênh: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@router.post("/publish", response_model=PublishShortsResponse)
async def publish_shorts(req: PublishShortsRequest, current_user=Depends(get_current_user)):
    """Xuất bản một video lên Kênh YouTube Shorts."""
    return await service.publish_shorts(user_id=_get_user_id(current_user), req=req)


@router.post("/upload-and-publish", response_model=PublishShortsResponse)
async def upload_and_publish_shorts(
    file: UploadFile = File(..., description="File video từ máy tính"),
    channel_id: str = Form(..., description="ID Kênh YouTube đích"),
    title: str = Form(..., description="Tiêu đề video"),
    description: str = Form("", description="Mô tả và Hashtags"),
    privacy_status: str = Form("public", description="Quyền riêng tư: public | unlisted | private"),
    video_type: str = Form("video", description="Loại xuất bản: video (dài) hoặc shorts (ngắn)"),
    current_user=Depends(get_current_user),
):
    """Tải file video trực tiếp từ máy tính lên và xuất bản lên YouTube."""
    import uuid
    from src.core.config import settings

    filename = file.filename or "video.mp4"
    if not filename.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file video định dạng (.mp4, .mov, .webm, .mkv)")

    temp_dir = settings.TEMP_DIR / "youtube_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"yt_{uuid.uuid4().hex[:8]}_{filename}"

    try:
        content = await file.read()
        temp_path.write_bytes(content)

        req = PublishShortsRequest(
            channel_id=channel_id,
            video_path=str(temp_path),
            title=title,
            description=description,
            privacy_status=privacy_status,
            video_type=video_type,
        )
        return await service.publish_shorts(user_id=_get_user_id(current_user), req=req)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass


@router.delete("/channels/{channel_id}/videos/{video_id}", response_model=DeleteYouTubeVideoResponse)
async def delete_channel_video(
    channel_id: str,
    video_id: str,
    current_user=Depends(get_current_user),
):
    """Xóa vĩnh viễn video khỏi Kênh YouTube, giữ lại thông tin trong DB để chống cào/đăng lại."""
    try:
        return await service.delete_video(
            user_id=_get_user_id(current_user),
            channel_id=channel_id,
            video_id=video_id,
        )
    except Exception as ex:
        logger.error(f"Lỗi xóa video YouTube {video_id}: {ex}")
        raise HTTPException(status_code=400, detail=str(ex))


@router.delete("/channels/{channel_id}")
async def disconnect_single_channel(channel_id: str, current_user=Depends(get_current_user)):
    """Hủy liên kết một Kênh YouTube cụ thể."""
    try:
        success = await service.disconnect(
            user_id=_get_user_id(current_user), channel_id=channel_id
        )
        return {"success": success, "message": f"Đã hủy liên kết Kênh {channel_id}"}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@router.delete("/disconnect")
async def disconnect_channel(current_user=Depends(get_current_user)):
    """Hủy liên kết tất cả Kênh YouTube."""
    try:
        success = await service.disconnect(user_id=_get_user_id(current_user))
        return {"success": success, "message": "Đã hủy liên kết Kênh YouTube"}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))
