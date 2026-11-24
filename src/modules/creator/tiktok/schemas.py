from typing import Optional, List
from pydantic import BaseModel, Field


class TikTokAuthUrlResponse(BaseModel):
    auth_url: str = Field(..., description="Đường dẫn ủy quyền TikTok OAuth v2")


class TikTokChannelItem(BaseModel):
    id: Optional[str] = None
    channel_id: str = Field(..., description="Open ID / Union ID của tài khoản TikTok")
    display_name: str = Field(..., description="Tên hiển thị tài khoản TikTok")
    username: Optional[str] = Field(None, description="TikTok Username (@username)")
    avatar_url: Optional[str] = Field(None, description="Ảnh đại diện TikTok")
    follower_count: int = Field(0, description="Số người theo dõi")
    likes_count: int = Field(0, description="Tổng số lượt thích")
    video_count: int = Field(0, description="Tổng số video đã đăng")
    scope: Optional[str] = Field(None, description="Danh sách quyền đã được cấp")
    is_active: bool = Field(True, description="Trạng thái kết nối kênh")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TikTokChannelListResponse(BaseModel):
    channels: List[TikTokChannelItem] = Field(default_factory=list)
    total: int = 0


class PublishTikTokRequest(BaseModel):
    channel_id: str = Field(..., description="ID kênh TikTok muốn đăng video")
    video_url: Optional[str] = Field(None, description="URL video trực tuyến (Cloudinary hoặc máy chủ)")
    title: str = Field(..., max_length=150, description="Tiêu đề và hashtag mô tả video")
    privacy_level: str = Field(
        "PUBLIC_TO_EVERYONE",
        description="Quyền riêng tư: PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, SELF_ONLY",
    )
    disable_duet: bool = Field(False, description="Tắt tính năng Duet")
    disable_comment: bool = Field(False, description="Tắt tính năng bình luận")
    disable_stitch: bool = Field(False, description="Tắt tính năng Stitch")
    video_cover_timestamp_ms: int = Field(1000, description="Mốc thời gian lấy ảnh bìa video (ms)")


class PublishTikTokResponse(BaseModel):
    publish_id: str = Field(..., description="Publish ID hoặc Share ID từ TikTok API")
    channel_id: str
    status: str = Field(..., description="Trạng thái khởi tạo đăng video (PROCESSING, SUCCESS)")
    title: str
    uploaded_at: str
    message: Optional[str] = None


class TikTokVideoItem(BaseModel):
    id: str = Field(..., description="ID của video trên TikTok")
    title: str = Field(default="", description="Tiêu đề / Caption video")
    cover_image_url: Optional[str] = Field(None, description="Ảnh bìa video")
    share_url: Optional[str] = Field(None, description="Link xem video trực tiếp trên TikTok")
    duration: int = Field(0, description="Độ dài video (giây)")
    view_count: int = Field(0, description="Lượt xem")
    like_count: int = Field(0, description="Lượt thích")
    comment_count: int = Field(0, description="Lượt bình luận")
    share_count: int = Field(0, description="Lượt chia sẻ")
    create_time: Optional[int] = Field(None, description="Timestamp tạo video")


class TikTokVideoListResponse(BaseModel):
    videos: List[TikTokVideoItem] = Field(default_factory=list)
    cursor: Optional[int] = None
    has_more: bool = False

