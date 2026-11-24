from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from typing import Optional, List, Dict, Any
from src.modules.shared.auth.dependencies import get_current_user
from .schemas import (
    ImageInspectRequest,
    ImageInspectResponse,
    TextPolicyInspectRequest,
    TextPolicyInspectResponse,
    VideoInspectRequest,
    VideoInspectResponse,
    InspectorHistoryItem,
)
from .service import InspectorService

inspector_router = APIRouter(prefix="/inspector", tags=["Creator - Viral & Policy Inspector"])


def get_inspector_service() -> InspectorService:
    return InspectorService()


@inspector_router.post(
    "/analyze-image",
    response_model=ImageInspectResponse,
    summary="Thẩm định ảnh bìa / ảnh chụp màn hình dự đoán độ HOT và vi phạm",
)
async def analyze_image_endpoint(
    payload: ImageInspectRequest,
    current_user: dict = Depends(get_current_user),
    service: InspectorService = Depends(get_inspector_service),
):
    try:
        user_id = str(current_user["id"])
        return await service.inspect_image_payload(
            user_id=user_id,
            image_base64=payload.image_base64,
            image_url=payload.image_url,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi thẩm định ảnh: {str(exc)}",
        )


@inspector_router.post(
    "/upload-image",
    response_model=ImageInspectResponse,
    summary="Upload file ảnh trực tiếp để thẩm định",
)
async def upload_image_endpoint(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    service: InspectorService = Depends(get_inspector_service),
):
    try:
        user_id = str(current_user["id"])
        contents = await file.read()
        return await service.inspect_image_bytes(
            user_id=user_id,
            image_bytes=contents,
            filename=file.filename or "uploaded.jpg",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi xử lý file ảnh tải lên: {str(exc)}",
        )


@inspector_router.post(
    "/analyze-text",
    response_model=TextPolicyInspectResponse,
    summary="Quét kịch bản/phụ đề tìm từ khóa cấm và gợi ý né gậy TikTok/FB",
)
async def analyze_text_endpoint(
    payload: TextPolicyInspectRequest,
    current_user: dict = Depends(get_current_user),
    service: InspectorService = Depends(get_inspector_service),
):
    try:
        user_id = str(current_user["id"])
        return await service.inspect_text(user_id=user_id, text=payload.text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi quét kịch bản: {str(exc)}",
        )


@inspector_router.post(
    "/analyze-video",
    response_model=VideoInspectResponse,
    summary="Thẩm định nhịp độ giữ chân (Pacing) và chính sách video",
)
async def analyze_video_endpoint(
    payload: VideoInspectRequest,
    current_user: dict = Depends(get_current_user),
    service: InspectorService = Depends(get_inspector_service),
):
    try:
        user_id = str(current_user["id"])
        return await service.inspect_video(
            user_id=user_id, job_id=payload.job_id, video_url=payload.video_url
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi thẩm định video: {str(exc)}",
        )


@inspector_router.get(
    "/history",
    response_model=List[Dict[str, Any]],
    summary="Lấy lịch sử các lần thẩm định",
)
async def get_history_endpoint(
    current_user: dict = Depends(get_current_user),
    service: InspectorService = Depends(get_inspector_service),
):
    user_id = str(current_user["id"])
    return await service.repo.get_history(user_id=user_id, limit=20)

