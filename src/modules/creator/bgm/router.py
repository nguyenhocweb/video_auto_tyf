import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from src.core.config import settings
from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.bgm.schemas import BgmListResponse, BgmTrackResponse, CopyrightCheckResponse
from src.modules.creator.bgm.service import BgmService

bgm_router = APIRouter(prefix="/bgm", tags=["Creator - Kho Nhạc Nền (BGM Library)"])


def get_bgm_service() -> BgmService:
    return BgmService()


@bgm_router.get("", response_model=BgmListResponse)
async def list_bgm_tracks(
    mood: Optional[str] = Query(None, description="Lọc theo mood: chill, upbeat, funny, asmr, cinematic, general"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service: BgmService = Depends(get_bgm_service),
):
    """Lấy danh sách bài nhạc nền (Bao gồm nhạc mẫu bản quyền sạch + nhạc của user)."""
    user_id = str(current_user.get("id") or current_user.get("_id", ""))
    return await service.list_tracks(user_id=user_id, mood=mood, skip=skip, limit=limit)


@bgm_router.post("/upload", response_model=BgmTrackResponse, status_code=status.HTTP_201_CREATED)
async def upload_bgm_track(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    mood: str = Form("chill"),
    tags: str = Form(""),
    start_time: Optional[float] = Form(None),
    end_time: Optional[float] = Form(None),
    sanitize_audio: bool = Form(True),
    current_user: dict = Depends(get_current_user),
    service: BgmService = Depends(get_bgm_service),
):
    """Tải lên bản nhạc nền người dùng tự thêm (Hỗ trợ cắt đoạn và khử bản quyền DSP)."""
    user_id = str(current_user.get("id") or current_user.get("_id", ""))
    return await service.upload_bgm(
        file=file,
        user_id=user_id,
        title=title,
        mood=mood,
        tags_str=tags,
        start_time=start_time,
        end_time=end_time,
        sanitize_audio=sanitize_audio,
    )


@bgm_router.post("/check-copyright", response_model=CopyrightCheckResponse)
async def check_copyright_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    service: BgmService = Depends(get_bgm_service),
):
    """Quét và thẩm định bản quyền âm thanh trực tiếp từ file trước khi lưu."""
    return await service.check_copyright_by_file(file=file)


@bgm_router.get("/{track_id}/check-copyright", response_model=CopyrightCheckResponse)
async def check_copyright_track(
    track_id: str,
    current_user: dict = Depends(get_current_user),
    service: BgmService = Depends(get_bgm_service),
):
    """Quét và thẩm định bản quyền của một bài nhạc đang có sẵn trong kho."""
    try:
        return await service.check_copyright_by_track_id(track_id=track_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@bgm_router.get("/random", response_model=Optional[BgmTrackResponse])
async def get_random_bgm(
    mood: Optional[str] = Query(None),
    preferred_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: BgmService = Depends(get_bgm_service),
):
    """Lấy ngẫu nhiên 1 bản nhạc cho tác vụ Auto Re-up."""
    user_id = str(current_user.get("id") or current_user.get("_id", ""))
    track = await service.get_random_bgm_for_auto(user_id=user_id, mood=mood, preferred_id=preferred_id)
    if not track:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài nhạc phù hợp trong kho.")
    return track


@bgm_router.get("/stream/{filename}")
async def stream_local_bgm(filename: str):
    """Phát trực tuyến bài nhạc local đã lưu trên máy chủ."""
    target_path = settings.BGM_STORAGE_DIR / Path(filename).name
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file nhạc này trên máy chủ.")
    media_type = "audio/mpeg" if target_path.suffix == ".mp3" else "audio/wav"
    return FileResponse(path=str(target_path), media_type=media_type)


@bgm_router.delete("/{track_id}")
async def delete_bgm_track(
    track_id: str,
    current_user: dict = Depends(get_current_user),
    service: BgmService = Depends(get_bgm_service),
):
    """Xóa bài nhạc người dùng tự thêm (Không thể xóa preset hệ thống)."""
    user_id = str(current_user.get("id") or current_user.get("_id", ""))
    success = await service.delete_track(track_id=track_id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Không thể xóa bài nhạc này (Preset hệ thống hoặc không tồn tại).")
    return {"message": "Đã xóa bài nhạc thành công."}
