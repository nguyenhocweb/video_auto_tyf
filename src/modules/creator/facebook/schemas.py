from typing import List, Optional, Any
from pydantic import BaseModel, Field


class FacebookPageItem(BaseModel):
    id: str
    name: str
    category: Optional[str] = "General"
    picture_url: Optional[str] = ""
    fan_count: int = 0
    followers_count: int = 0
    access_token: Optional[str] = ""


class FacebookVideoItem(BaseModel):
    id: str
    title: Optional[str] = ""
    description: Optional[str] = ""
    created_time: Optional[str] = ""
    thumbnail: Optional[str] = ""
    permalink_url: Optional[str] = ""
    length: float = 0.0
    views: int = 0
    reactions_count: int = 0
    comments_count: int = 0


class FacebookPostItem(BaseModel):
    id: str
    message: Optional[str] = ""
    created_time: Optional[str] = ""
    thumbnail: Optional[str] = ""
    permalink_url: Optional[str] = ""
    shares_count: int = 0
    reactions_count: int = 0
    comments_count: int = 0


class AvailableVideoItem(BaseModel):
    id: str
    name: str
    path: str
    size_mb: float
    source: str
    modified_time: str


class PublishReelRequest(BaseModel):
    page_id: Optional[str] = Field(None, description="ID Fanpage đích (mặc định lấy cấu hình)")
    video_path: str = Field(..., description="Đường dẫn file video mp4 trên máy chủ hoặc URL")
    caption: str = Field("", description="Tiêu đề và nội dung bài viết kèm theo")
    title: Optional[str] = Field("", description="Tiêu đề video")
    post_type: Optional[str] = Field("reel", description="Loại xuất bản: 'reel' (Thước phim) hoặc 'feed' (Bài viết)")
    access_token: Optional[str] = Field(None, description="Page Access Token tùy chọn")


class PublishReelResponse(BaseModel):
    success: bool
    video_id: str
    page_id: str
    page_name: str
    caption: str
    reel_url: str
    post_type: Optional[str] = "reel"
    message: str = "Xuất bản Facebook thành công!"


class TokenStatusResponse(BaseModel):
    is_valid: bool
    has_token: bool = True
    error: Optional[str] = None
    expires_at: Optional[int] = None
    scopes: List[str] = []
    expires_in_days: Optional[float] = None
    expires_at_formatted: Optional[str] = "Chưa xác định"
    token_type_label: Optional[str] = "User Token"
    data_access_expires_at: Optional[int] = None


class UpdateTokenRequest(BaseModel):
    user_token: str = Field(..., min_length=10, description="User Access Token từ Meta Graph Explorer")


