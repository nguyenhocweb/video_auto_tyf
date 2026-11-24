from typing import Optional, List
from pydantic import BaseModel, Field


class YouTubeAuthUrlResponse(BaseModel):
    auth_url: str


class YouTubeChannelItem(BaseModel):
    id: Optional[str] = None
    channel_id: str = ""
    channel_title: str = "Kênh YouTube"
    google_email: Optional[str] = None
    custom_url: Optional[str] = None
    avatar_url: Optional[str] = None
    subscriber_count: int = 0
    video_count: int = 0
    has_refresh_token: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class YouTubeChannelListResponse(BaseModel):
    total: int
    channels: List[YouTubeChannelItem]


class YouTubeChannelResponse(BaseModel):
    is_connected: bool
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    google_email: Optional[str] = None
    custom_url: Optional[str] = None
    avatar_url: Optional[str] = None
    subscriber_count: Optional[int] = 0
    video_count: Optional[int] = 0
    has_refresh_token: bool = False
    error: Optional[str] = None


class YouTubeVideoItem(BaseModel):
    id: str
    title: str
    description: Optional[str] = ""
    thumbnail: Optional[str] = None
    published_at: Optional[str] = None
    views: int = 0
    likes: int = 0
    comments: int = 0
    duration: Optional[str] = ""
    privacy_status: Optional[str] = "public"
    restriction: Optional[str] = "none"
    restriction_detail: Optional[str] = None
    is_deleted: bool = False
    shorts_url: str
    watch_url: str


class DeleteYouTubeVideoResponse(BaseModel):
    success: bool
    video_id: str
    message: str
    blacklisted: bool = True


class YouTubeVideoListResponse(BaseModel):
    total: int
    videos: List[YouTubeVideoItem]


class AvailableVideoItem(BaseModel):
    filename: str
    path: str
    title: str
    size_mb: float
    created_at: str
    source_type: str


class PublishShortsRequest(BaseModel):
    channel_id: Optional[str] = Field(None, description="ID Kênh YouTube cụ thể muốn đăng")
    video_path: Optional[str] = None
    video_url: Optional[str] = None
    title: str = Field(..., max_length=100, description="Tiêu đề video YouTube")
    description: Optional[str] = ""
    tags: Optional[List[str]] = None
    privacy_status: Optional[str] = "public"
    video_type: Optional[str] = Field("video", description="Loại xuất bản: 'video' (Video dài/thường) hoặc 'shorts' (Video ngắn)")


class PublishShortsResponse(BaseModel):
    success: bool
    channel_id: Optional[str] = None
    video_id: Optional[str] = None
    shorts_url: Optional[str] = None
    watch_url: Optional[str] = None
    video_url: Optional[str] = None
    video_type: Optional[str] = "video"
    title: Optional[str] = None
    error: Optional[str] = None
