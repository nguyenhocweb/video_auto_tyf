"""Schemas Pydantic cho Creator Template Video API.
Tuân thủ giới hạn tối đa 300 dòng và chuẩn type hinting Pydantic v2.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SlotItemResponse(BaseModel):
    """Thông tin chi tiết của 1 Slot đầu vào."""
    slot_id: int
    slot_type: str
    title: str
    description: str
    start_time: float
    duration: float
    required: bool


class TemplateItemResponse(BaseModel):
    """Chi tiết 1 mẫu video trả về cho Frontend."""
    template_id: str
    name: str
    description: str
    category: str
    version: str
    total_duration: float
    width: int
    height: int
    fps: int
    slots: List[SlotItemResponse]
    default_bgm: Optional[str] = None


class TemplateListResponse(BaseModel):
    """Danh sách các mẫu video hỗ trợ."""
    total: int
    items: List[TemplateItemResponse]


class TemplateRenderResponse(BaseModel):
    """Kết quả phản hồi sau khi render video mẫu."""
    success: bool
    template_id: str
    filename: str
    stream_url: str
    download_url: str
    duration: float
    file_size_mb: float
    elapsed_seconds: float
    fps_rendered: float
    encoder_used: str
    beat_count: int
    message: str = "Render video mẫu thành công!"


class ParseTemplateRequest(BaseModel):
    """Request bóc tách kịch bản từ link hoặc ID mẫu CapCut."""
    url_or_id: str = Field(..., description="Link CapCut hoặc ID mẫu")


class ParsedSlotResponse(BaseModel):
    """Chi tiết 1 slot được bóc tách tự động."""
    slot_id: int
    slot_type: str
    start_time: float
    end_time: float
    duration: float
    description: str = ""
    is_replaceable: bool = True
    video_width: Optional[int] = None
    video_height: Optional[int] = None


class ParsedTemplateResponse(BaseModel):
    """Kết quả bóc tách kịch bản mẫu CapCut động."""
    success: bool = True
    template_id: str
    title: str
    author_name: str = "CapCut Creator"
    total_duration: float
    total_slots: int
    image_slots_count: int
    video_slots_count: int
    slots: List[ParsedSlotResponse]
    has_audio: bool = True
    music_title: Optional[str] = None
    cover_url: Optional[str] = None
    video_url: Optional[str] = None
    template_url: Optional[str] = None
    source_url: Optional[str] = None
    is_saved_in_db: bool = False
    message: str = "Đã phân tích kịch bản mẫu thành công!"


class SaveTemplateDbRequest(BaseModel):
    """Request lưu mẫu CapCut vào CSDL MongoDB."""
    template_id: str
    title: str
    author_name: Optional[str] = "CapCut Creator"
    total_duration: float
    total_slots: int
    image_slots_count: int
    video_slots_count: int
    slots: List[ParsedSlotResponse]
    cover_url: Optional[str] = None
    video_url: Optional[str] = None
    template_url: Optional[str] = None
    music_title: Optional[str] = None
    music_url: Optional[str] = None
    source_url: Optional[str] = None


class SavedTemplateDbItem(BaseModel):
    """1 mẫu CapCut đã lưu trong MongoDB."""
    id: Optional[str] = None
    template_id: str
    title: str
    author_name: str = "CapCut Creator"
    total_duration: float
    total_slots: int
    image_slots_count: int
    video_slots_count: int
    slots: List[ParsedSlotResponse]
    cover_url: Optional[str] = None
    video_url: Optional[str] = None
    template_url: Optional[str] = None
    music_title: Optional[str] = None
    music_url: Optional[str] = None
    source_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SavedTemplateDbListResponse(BaseModel):
    """Danh sách mẫu CapCut lưu trong MongoDB."""
    total: int
    items: List[SavedTemplateDbItem]


class DeleteTemplateDbResponse(BaseModel):
    """Kết quả xóa mẫu CapCut khỏi MongoDB."""
    success: bool
    template_id: str
    message: str


class CreateCapCutDesktopResponse(BaseModel):
    """Kết quả tạo dự án CapCut PC từ mẫu gốc."""
    success: bool
    template_id: str
    project_name: str
    project_path: str
    total_duration: float
    slots_count: int
    message: str


class LaunchCapCutRequest(BaseModel):
    """Yêu cầu mở CapCut PC hoặc mở thư mục dự án."""
    project_path: Optional[str] = None


class LaunchCapCutResponse(BaseModel):
    """Kết quả mở app CapCut hoặc thư mục."""
    success: bool
    message: str

