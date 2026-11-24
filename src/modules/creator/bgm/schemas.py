from typing import List, Optional
from pydantic import BaseModel, Field


class BgmTrackResponse(BaseModel):
    """Thông tin bài nhạc nền trong kho BGM."""
    id: str
    user_id: Optional[str] = None
    title: str
    mood: str = Field(default="chill", description="chill, upbeat, funny, asmr, cinematic, general")
    duration: float = Field(default=0.0, description="Thời lượng bản nhạc tính theo giây")
    audio_url: str
    file_path: Optional[str] = None
    is_preset: bool = False
    sanitized: bool = Field(default=False, description="Đã được làm sạch sóng âm chống bản quyền hay chưa")
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BgmRandomPickRequest(BaseModel):
    """Yêu cầu chọn ngẫu nhiên bài nhạc nền theo mood."""
    mood: Optional[str] = Field(None, description="Thể loại cảm xúc muốn lấy")
    preferred_id: Optional[str] = Field(None, description="ID bài nhạc muốn chỉ định rõ")


class BgmListResponse(BaseModel):
    """Phản hồi danh sách bài nhạc kèm phân trang."""
    items: List[BgmTrackResponse]
    total: int
    moods: List[str]


class CopyrightCheckResponse(BaseModel):
    """Kết quả thẩm định quét bản quyền âm thanh số."""
    has_copyright: bool
    risk_level: str = Field(default="safe", description="safe, warning, danger")
    matched_title: Optional[str] = None
    matched_artist: Optional[str] = None
    matched_label: Optional[str] = None
    confidence: float = 0.0
    duration: float = 0.0
    is_sanitized: bool = False
    details: str
    recommendation: str
