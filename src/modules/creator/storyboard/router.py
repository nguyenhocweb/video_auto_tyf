import os
import mimetypes
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, status
from fastapi.responses import FileResponse
from src.modules.creator.storyboard.schemas import (
    ScriptGenerateRequest,
    ScriptGenerateResponse,
    RenderStoryboardRequest,
    RenderStoryboardResponse,
    CleanWatermarkRequest,
    CleanWatermarkResponse,
    BatchCleanRequest,
    BatchCleanResponse,
    VoiceOptionsResponse,
    StoryboardPublishRequest,
    StoryboardPublishResponse,
)
from src.modules.creator.storyboard.service import (
    StoryboardService,
    STORYBOARD_STORAGE,
    _FALLBACK_STORYBOARD_STORAGE,
)
from src.modules.creator.storyboard.publisher import StoryboardPublisher

logger = logging.getLogger("storyboard_router")

storyboard_router = APIRouter(prefix="/storyboard", tags=["Creator - AI Storyboard Studio"])

@storyboard_router.get(
    "/voices",
    response_model=VoiceOptionsResponse,
    summary="Lấy danh sách các giọng đọc mặc định và model giọng nói đã training",
)
async def get_available_voices_endpoint():
    try:
        voices = await StoryboardService.get_available_voices()
        return VoiceOptionsResponse(success=True, voices=voices)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi lấy danh sách giọng: {str(exc)}",
        )

@storyboard_router.post(
    "/generate-script",
    response_model=ScriptGenerateResponse,
    summary="AI Tự động sinh kịch bản và câu Prompt vẽ ảnh chuẩn DNA nhân vật",
)
async def generate_script_endpoint(payload: ScriptGenerateRequest):
    try:
        return await StoryboardService.generate_script(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi sinh kịch bản: {str(exc)}",
        )

@storyboard_router.post(
    "/upload-image",
    summary="Tải ảnh lên cho từng phân cảnh của kịch bản",
)
async def upload_image_endpoint(
    job_id: str = Form(...),
    scene_idx: int = Form(...),
    file: UploadFile = File(...),
    auto_clean: bool = Form(False),
):
    try:
        content = await file.read()
        res = await StoryboardService.save_uploaded_image(
            job_id=job_id,
            scene_idx=scene_idx,
            file_bytes=content,
            filename=file.filename or "image.jpg",
            auto_clean=auto_clean,
        )
        return {"success": True, "scene_idx": scene_idx, **res}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi lưu ảnh phân cảnh: {str(exc)}",
        )

@storyboard_router.post(
    "/clean-watermark",
    response_model=CleanWatermarkResponse,
    summary="Tẩy sạch Watermark & Logo AI trên ảnh của phân cảnh cụ thể",
)
async def clean_watermark_endpoint(payload: CleanWatermarkRequest):
    try:
        res = await StoryboardService.clean_scene_watermark(
            job_id=payload.job_id,
            scene_idx=payload.scene_idx,
            watermark_type=payload.watermark_type,
            custom_box=payload.custom_box,
        )
        return CleanWatermarkResponse(
            success=True,
            scene_idx=payload.scene_idx,
            url=res["url"],
            path=res["path"],
            detected=res["detected"],
            message="Đã tẩy sạch watermark thành công",
        )
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xóa watermark: {str(exc)}",
        )

@storyboard_router.post(
    "/batch-clean-watermarks",
    response_model=BatchCleanResponse,
    summary="Tẩy sạch Watermark & Logo hàng loạt trên toàn bộ các cảnh của dự án",
)
async def batch_clean_watermarks_endpoint(payload: BatchCleanRequest):
    try:
        res = await StoryboardService.batch_clean_scenes(
            job_id=payload.job_id,
            scene_indices=payload.scene_indices,
        )
        return BatchCleanResponse(
            success=True,
            cleaned_count=res["cleaned_count"],
            scenes=res["scenes"],
            message=f"Đã làm sạch watermark thành công cho {res['cleaned_count']} phân cảnh",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xóa watermark hàng loạt: {str(exc)}",
        )

@storyboard_router.post(
    "/render-video",
    response_model=RenderStoryboardResponse,
    summary="Tự động lồng tiếng AI, căn chỉnh thời lượng và kết xuất video hoàn chỉnh",
)
async def render_video_endpoint(payload: RenderStoryboardRequest):
    try:
        return await StoryboardService.render_video(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi render video storyboard: {str(exc)}",
        )

@storyboard_router.get(
    "/media/{job_id}/{subfolder}/{filename}",
    summary="Xem hoặc tải về ảnh phân cảnh hoặc video thành phẩm",
)
async def get_storyboard_media_endpoint(job_id: str, subfolder: str, filename: str):
    file_path = os.path.join(STORYBOARD_STORAGE, job_id, subfolder, filename)
    if not os.path.exists(file_path):
        fb_path = os.path.join(_FALLBACK_STORYBOARD_STORAGE, job_id, subfolder, filename)
        if os.path.exists(fb_path):
            file_path = fb_path
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tệp phương tiện không tồn tại hoặc đã bị xóa.",
            )

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        if filename.endswith(".mp4"):
            mime_type = "video/mp4"
        elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
            mime_type = "image/jpeg"
        elif filename.endswith(".png"):
            mime_type = "image/png"
        else:
            mime_type = "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=filename,
    )

async def _resolve_user_id(authorization: Optional[str] = None) -> str:
    """Trích xuất User ID từ JWT Header nếu có, mặc định là default_user."""
    if authorization and authorization.startswith("Bearer "):
        try:
            from src.modules.shared.auth.security import decode_access_token
            token = authorization.split(" ")[1]
            payload = decode_access_token(token)
            if payload and "sub" in payload:
                return str(payload["sub"])
        except Exception:
            pass
    return "default_user"

@storyboard_router.post(
    "/publish-video",
    response_model=StoryboardPublishResponse,
    summary="Đăng video Storyboard lên YouTube Shorts, Facebook Reels hoặc TikTok",
)
async def publish_video_endpoint(
    payload: StoryboardPublishRequest,
    authorization: Optional[str] = Header(None),
):
    try:
        user_id = await _resolve_user_id(authorization)
        return await StoryboardPublisher.publish(user_id=user_id, req=payload)
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf),
        )
    except Exception as exc:
        logger.error(f"Lỗi khi xuất bản video Storyboard: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
