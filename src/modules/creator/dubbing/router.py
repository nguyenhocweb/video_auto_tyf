import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse

from src.core.config import settings
from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.dubbing.schemas import (
    DubbingTranscribeRequest,
    DubbingTranscribeResponse,
    DubbingTranslateRequest,
    DubbingTranslateResponse,
    DubbingRenderRequest,
    AutoDubbingFromUrlRequest,
    DubbingCleanVideoRequest,
    DubbingJobResponse,
    TranslateContentRequest,
    TranslateContentResponse,
)
from src.modules.creator.dubbing.service import DubbingService
from src.modules.creator.dubbing.repository import DubbingMongoRepository

router = APIRouter(prefix="/dubbing", tags=["Creator - Vietsub & Dubbing"])


def get_dubbing_service() -> DubbingService:
    return DubbingService()


@router.post(
    "/auto-from-url",
    response_model=DubbingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Tự động bóc tách link Douyin, xóa phụ đề cứng, dịch và lồng tiếng chạy ngầm",
)
async def auto_from_url_endpoint(
    payload: AutoDubbingFromUrlRequest,
    current_user: dict = Depends(get_current_user),
    service: DubbingService = Depends(get_dubbing_service),
) -> DubbingJobResponse:
    try:
        return await service.enqueue_auto_dubbing_from_url(payload, current_user["id"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi tiếp nhận yêu cầu: {str(exc)}",
        )


@router.post(
    "/transcribe",
    response_model=DubbingTranscribeResponse,
    status_code=status.HTTP_200_OK,
    summary="Bóc tách lời thoại và sinh timeline phụ đề bằng Faster-Whisper",
)
async def transcribe_endpoint(
    payload: DubbingTranscribeRequest,
    current_user: dict = Depends(get_current_user),
    service: DubbingService = Depends(get_dubbing_service),
) -> DubbingTranscribeResponse:
    try:
        return await service.transcribe_video(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi bóc tách âm thanh video: {str(exc)}",
        )


@router.post(
    "/translate",
    response_model=DubbingTranslateResponse,
    status_code=status.HTTP_200_OK,
    summary="Dịch nội dung phụ đề từ tiếng Trung sang tiếng Việt",
)
async def translate_endpoint(
    payload: DubbingTranslateRequest,
    current_user: dict = Depends(get_current_user),
    service: DubbingService = Depends(get_dubbing_service),
) -> DubbingTranslateResponse:
    try:
        return await service.translate_segments(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi dịch phụ đề: {str(exc)}",
        )


@router.post(
    "/translate-content",
    response_model=TranslateContentResponse,
    status_code=status.HTTP_200_OK,
    summary="Dịch tiêu đề và nội dung mô tả video sang tiếng Việt",
)
async def translate_content_endpoint(
    payload: TranslateContentRequest,
    current_user: dict = Depends(get_current_user),
) -> TranslateContentResponse:
    try:
        from src.core.utils.content_translator import ContentTranslator

        trans_title, trans_caption = await ContentTranslator.translate_title_and_caption(
            title=payload.title or "",
            caption=payload.caption or "",
        )
        return TranslateContentResponse(title=trans_title, caption=trans_caption)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi dịch nội dung: {str(exc)}",
        )


@router.post(
    "/clean-subtitles",
    response_model=DubbingJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Xóa sạch phụ đề cứng tiếng Trung bằng AI Inpainting",
)
async def clean_subtitles_endpoint(
    payload: DubbingCleanVideoRequest,
    current_user: dict = Depends(get_current_user),
    service: DubbingService = Depends(get_dubbing_service),
) -> DubbingJobResponse:
    try:
        return await service.clean_video_subtitles(payload, current_user["id"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xóa phụ đề cứng: {str(exc)}",
        )


@router.post(
    "/render",
    response_model=DubbingJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Khởi chạy render video theo 3 chế độ (Vietsub, Thuyết minh, Cả 2)",
)
async def render_endpoint(
    payload: DubbingRenderRequest,
    current_user: dict = Depends(get_current_user),
    service: DubbingService = Depends(get_dubbing_service),
) -> DubbingJobResponse:
    try:
        return await service.render_dubbing_job(payload, current_user["id"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi khởi chạy render video: {str(exc)}",
        )


@router.get(
    "/history",
    summary="Lấy danh sách các video đã tạo Vietsub / Dubbing của tài khoản (chỉ của chính mình)",
)
async def history_endpoint(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    repo = DubbingMongoRepository()
    skip = (page - 1) * limit
    total = await repo.count_user_jobs(current_user["id"])
    items = await repo.get_user_jobs(current_user["id"], skip=skip, limit=limit)
    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.delete(
    "/jobs/{job_id}",
    summary="Xóa tác vụ dubbing của người dùng",
)
async def delete_job_endpoint(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    service: DubbingService = Depends(get_dubbing_service),
):
    success = await service.delete_job(job_id, current_user["id"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tác vụ hoặc bạn không có quyền xóa tác vụ này.",
        )
    return {"message": "Đã xóa tác vụ thành công"}


@router.post(
    "/jobs/{job_id}/retry",
    response_model=DubbingJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Thử lại tác vụ dubbing bị lỗi hoặc bị gián đoạn",
)
async def retry_job_endpoint(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    service: DubbingService = Depends(get_dubbing_service),
) -> DubbingJobResponse:
    job = await service.retry_job(job_id, current_user["id"])
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tác vụ hoặc bạn không có quyền thử lại tác vụ này.",
        )
    return job


@router.get(
    "/download/{file_name}",
    summary="Tải hoặc xem trực tiếp video/phụ đề thành phẩm",
)
@router.get("/stream/{file_name}", summary="Stream video trực tiếp")
async def download_file_endpoint(file_name: str):
    file_path = settings.DUBBING_OUTPUT_DIR / file_name
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File không tồn tại.")

    media_type = "video/mp4"
    if file_name.endswith(".srt"):
        media_type = "text/plain"
    elif file_name.endswith(".ass"):
        media_type = "text/plain"

    return FileResponse(path=str(file_path), media_type=media_type, filename=file_name)


from src.modules.creator.dubbing.gemini_keys_router import gemini_keys_router
from src.modules.creator.dubbing.groq_keys_router import groq_keys_router
router.include_router(gemini_keys_router)
router.include_router(groq_keys_router)
