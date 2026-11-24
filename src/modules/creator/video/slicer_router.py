import os
import mimetypes
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from src.modules.creator.video.slicer_schemas import (
    SliceVideoToTemplateRequest,
    SliceVideoToTemplateResponse,
)
from src.modules.creator.video.slicer_service import VideoSlicerService

slicer_router = APIRouter()

@slicer_router.post(
    "/slice-to-template",
    response_model=SliceVideoToTemplateResponse,
    summary="AI Giai phau video thanh bo anh va clip dung chuan cac slot cua Mau",
)
async def slice_video_to_template_endpoint(
    payload: SliceVideoToTemplateRequest,
):
    try:
        return await VideoSlicerService.process_slice(payload)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Loi khi giai phau video: {str(exc)}",
        )

@slicer_router.get(
    "/slicer-assets/{job_id}/{file_name}",
    summary="Xem hoac tai ve anh, clip con hoac file zip tai nguyen",
)
async def get_slicer_asset_endpoint(job_id: str, file_name: str):
    file_path = os.path.join(VideoSlicerService.STORAGE_BASE, f"slicer_{job_id}", file_name)
    if not os.path.exists(file_path):
        alt_path = os.path.join("be", file_path)
        if os.path.exists(alt_path):
            file_path = alt_path
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tep tai nguyen khong ton tai hoac da bi don dep.",
            )

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        if file_name.endswith(".zip"):
            mime_type = "application/zip"
        elif file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
            mime_type = "image/jpeg"
        elif file_name.endswith(".mp4"):
            mime_type = "video/mp4"
        else:
            mime_type = "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=file_name,
    )

