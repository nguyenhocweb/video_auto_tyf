from typing import Optional, List
from pydantic import BaseModel, Field


class VideoExtractRequest(BaseModel):
    url: str = Field(..., description="Link video Douyin (dạng rút gọn v.douyin.com hoặc link web)")


class VideoAuthorInfo(BaseModel):
    nickname: str = Field(default="Douyin Creator", description="Tên tác giả video")
    avatar: Optional[str] = Field(default=None, description="URL ảnh đại diện tác giả")
    uid: Optional[str] = Field(default=None, description="UID tác giả")


class VideoMetadataResponse(BaseModel):
    item_id: str = Field(..., description="Mã định danh video Douyin")
    title: str = Field(default="", description="Tiêu đề / Caption của video")
    duration: float = Field(default=0.0, description="Thời lượng video (giây)")
    video_url: str = Field(..., description="Đường dẫn video MP4 không dính logo watermark")
    cover_url: Optional[str] = Field(default=None, description="Ảnh bìa thumbnail video")
    music_url: Optional[str] = Field(default=None, description="Đường dẫn âm thanh nền gốc")
    author: VideoAuthorInfo = Field(default_factory=VideoAuthorInfo)
    source_platform: str = Field(default="douyin", description="Nền tảng nguồn")


class VideoSaveRequest(BaseModel):
    item_id: str = Field(..., description="Mã ID video")
    title: str = Field(default="Video không tiêu đề")
    duration: float = Field(default=0.0)
    video_url: str = Field(..., description="URL video không logo")
    cover_url: Optional[str] = Field(default=None)
    music_url: Optional[str] = Field(default=None)
    author_name: Optional[str] = Field(default="Douyin Creator")
    author_avatar: Optional[str] = Field(default=None)


class VideoRecordResponse(BaseModel):
    id: str = Field(..., description="ID bản ghi trong database")
    user_id: str = Field(...)
    item_id: str = Field(...)
    title: str
    duration: float
    video_url: str
    cover_url: Optional[str] = None
    music_url: Optional[str] = None
    author_name: Optional[str] = None
    author_avatar: Optional[str] = None
    cloudinary_url: Optional[str] = None
    created_at: str


class VideoPaginationResponse(BaseModel):
    items: List[VideoRecordResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class ChannelCrawlRequest(BaseModel):
    url: str = Field(..., description="Link kênh profile tác giả hoặc link video bất kỳ của tác giả")
    limit: int = Field(default=20, ge=1, le=50, description="Số lượng video tối đa cần quét")


class ChannelVideoItem(BaseModel):
    item_id: str
    title: str
    video_url: str
    cover_url: Optional[str] = None
    is_today: bool = True
    crawled_date: str
    publish_time: Optional[str] = Field(default=None, description="Thời gian đăng cụ thể (vd: 06/11/2026 14:30)")
    created_timestamp: Optional[int] = None
    likes_count: Optional[int] = 0


class ChannelTodayVideosResponse(BaseModel):
    creator_name: str
    translated_name: Optional[str] = Field(default=None, description="Tên kênh đã được dịch sang tiếng Việt")
    creator_avatar: Optional[str] = None
    channel_url: str
    total_works: int
    today_count: int
    videos: List[ChannelVideoItem]


class SavedChannelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Tên hiển thị kênh (có thể đổi)")
    original_name: Optional[str] = Field(default="", description="Tên gốc từ Douyin")
    channel_url: str = Field(..., description="Đường link của kênh Douyin")
    avatar_url: Optional[str] = Field(default=None, description="Ảnh đại diện tác giả")
    total_works: Optional[int] = Field(default=0, description="Tổng số tác phẩm")


class SavedChannelUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Tên mới của kênh")


class SavedChannelResponse(BaseModel):
    id: str
    user_id: str
    name: str
    original_name: Optional[str] = ""
    channel_url: str
    avatar_url: Optional[str] = None
    total_works: Optional[int] = 0
    created_at: str
    updated_at: str


class SavedChannelListResponse(BaseModel):
    channels: List[SavedChannelResponse]
    total: int


