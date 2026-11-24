"""Router API cho Creator Template Video (Mẫu Video CapCut)."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from src.modules.creator.template_video.schemas import (
    CreateCapCutDesktopResponse,
    DeleteTemplateDbResponse,
    LaunchCapCutRequest,
    LaunchCapCutResponse,
    ParsedTemplateResponse,
    SaveTemplateDbRequest,
    SavedTemplateDbItem,
    SavedTemplateDbListResponse,
    TemplateItemResponse,
    TemplateListResponse,
    TemplateRenderResponse,
)
from src.modules.creator.template_video.service import TemplateVideoService
from src.modules.shared.auth.dependencies import get_current_user

template_video_router = APIRouter(
    prefix="/templates",
    tags=["Creator - Mẫu Video CapCut (Template Renderer)"],
)


def get_template_service() -> TemplateVideoService:
    return TemplateVideoService()


@template_video_router.get("", response_model=TemplateListResponse)
async def list_templates(
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Lấy danh sách các mẫu video hỗ trợ từ engine."""
    return service.list_templates()


@template_video_router.get("/db", response_model=SavedTemplateDbListResponse)
async def list_db_templates(
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Lấy danh sách các mẫu CapCut đã lưu trong CSDL MongoDB."""
    return await service.list_db_templates()


@template_video_router.get("/db/{template_id}", response_model=SavedTemplateDbItem)
async def get_db_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Lấy chi tiết 1 mẫu CapCut đã lưu trong CSDL MongoDB."""
    return await service.get_db_template(template_id)


@template_video_router.post("/db", response_model=SavedTemplateDbItem)
async def save_template_to_db(
    payload: SaveTemplateDbRequest,
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Lưu cấu trúc kịch bản mẫu CapCut vào CSDL MongoDB."""
    user_id = str(current_user.get("id") or current_user.get("_id", "creator"))
    return await service.save_template_to_db(user_id=user_id, payload=payload)


@template_video_router.delete("/db/{template_id}", response_model=DeleteTemplateDbResponse)
async def delete_db_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Xóa mẫu CapCut khỏi CSDL MongoDB."""
    user_id = str(current_user.get("id") or current_user.get("_id", "creator"))
    return await service.delete_db_template(template_id=template_id, user_id=user_id)


@template_video_router.get("/{template_id}", response_model=TemplateItemResponse)
async def get_template_detail(
    template_id: str,
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Lấy chi tiết 1 mẫu video theo ID từ engine."""
    return service.get_template(template_id)


@template_video_router.post("/parse", response_model=ParsedTemplateResponse)
async def parse_capcut_template(
    url_or_id: Optional[str] = Form(None),
    draft_file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Tự động bóc tách kịch bản mẫu CapCut từ Link/ID hoặc file draft."""
    return await service.parse_template(url_or_id=url_or_id, draft_file=draft_file)


@template_video_router.post("/render", response_model=TemplateRenderResponse)
async def render_template_video(
    template_id: str = Form("t01_beat_drop"),
    video_file: Optional[UploadFile] = File(None, description="Video cho Slot 1"),
    image_file: Optional[UploadFile] = File(None, description="Ảnh cho Slot 1 hoặc Slot 2"),
    image2_file: Optional[UploadFile] = File(None, description="Ảnh cho Slot 2"),
    image3_file: Optional[UploadFile] = File(None, description="Ảnh cho Slot 3"),
    slot_1: Optional[UploadFile] = File(None, description="File Slot 1"),
    slot_2: Optional[UploadFile] = File(None, description="File Slot 2"),
    slot_3: Optional[UploadFile] = File(None, description="File Slot 3"),
    slot_4: Optional[UploadFile] = File(None, description="File Slot 4"),
    audio_file: Optional[UploadFile] = File(None, description="File nhạc nền tùy chọn"),
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Render video mẫu từ Video/Ảnh và nhạc nền beat sync."""
    user_id = str(current_user.get("id") or current_user.get("_id", "creator"))
    raw_slots = {
        1: slot_1 or video_file or (image_file if template_id == "t02_three_photos" else None),
        2: slot_2 or (image_file if template_id != "t02_three_photos" else None) or image2_file,
        3: slot_3 or image3_file,
        4: slot_4 or audio_file,
    }
    slots_map = {k: v for k, v in raw_slots.items() if v is not None and getattr(v, "filename", None)}

    return await service.render_template(
        template_id=template_id,
        slots_files=slots_map,
        audio_file=audio_file or slots_map.get(4),
        user_id=user_id,
    )


@template_video_router.get("/stream/{filename}")
async def stream_rendered_video(filename: str):
    """Stream xem trước video đã render trên trình duyệt."""
    file_path = Path("be/storage/temp/templates_output") / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Video không tồn tại hoặc đã bị xóa!")
    return FileResponse(path=str(file_path), media_type="video/mp4")


@template_video_router.get("/download/{filename}")
async def download_rendered_video(filename: str):
    """Tải xuống video đã render về máy tính."""
    file_path = Path("be/storage/temp/templates_output") / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Video không tồn tại hoặc đã bị xóa!")
    return FileResponse(path=str(file_path), media_type="video/mp4", filename=filename)


@template_video_router.post("/export-to-capcut-pc", response_model=CreateCapCutDesktopResponse)
async def export_to_capcut_desktop_project(
    template_id: str = Form(...),
    template_url: Optional[str] = Form(None),
    project_title: Optional[str] = Form(None),
    slot_1: Optional[UploadFile] = File(None),
    slot_2: Optional[UploadFile] = File(None),
    slot_3: Optional[UploadFile] = File(None),
    slot_4: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Tạo dự án CapCut PC 100% nguyên bản (16 hiệu ứng, sticker, nhạc gốc) và đăng ký vào app."""
    raw_slots = {1: slot_1, 2: slot_2, 3: slot_3, 4: slot_4}
    slots_map = {k: v for k, v in raw_slots.items() if v is not None and getattr(v, "filename", None)}
    return await service.create_capcut_desktop_project(
        template_id=template_id,
        template_url=template_url,
        project_title=project_title,
        slots_files=slots_map,
    )


@template_video_router.post("/launch-capcut", response_model=LaunchCapCutResponse)
async def launch_capcut_pc(
    payload: LaunchCapCutRequest,
    current_user: dict = Depends(get_current_user),
    service: TemplateVideoService = Depends(get_template_service),
):
    """Khởi chạy app CapCut PC hoặc mở thư mục dự án trên máy tính."""
    return await service.launch_capcut(project_path=payload.project_path)

