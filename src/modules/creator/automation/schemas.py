from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SourceChannelConfig(BaseModel):
    channel_url: str = Field(..., description="Link trang cá nhân kênh Douyin")
    name: str = Field(..., description="Tên kênh hiển thị")
    original_name: Optional[str] = Field(None, description="Tên gốc tiếng Trung của kênh")
    avatar_url: Optional[str] = Field(None, description="Avatar kênh")


class TargetPageConfig(BaseModel):
    page_id: str = Field(..., description="ID Fanpage Facebook")
    page_name: str = Field(..., description="Tên Fanpage Facebook")
    access_token: Optional[str] = Field(None, description="Page Access Token (nếu có)")


class TargetYouTubeChannelConfig(BaseModel):
    channel_id: str = Field(..., description="ID Kênh YouTube")
    channel_title: str = Field(..., description="Tên Kênh YouTube")
    avatar_url: Optional[str] = Field(None, description="Avatar kênh")


class DualSourceConfig(BaseModel):
    enabled: bool = Field(default=False, description="Bật chế độ ghép 2 nguồn (Hook + Body)")
    hook_channel_url: Optional[str] = Field(None, description="Link kênh nguồn 1 (Kênh Hook)")
    hook_channel_name: Optional[str] = Field(None, description="Tên kênh nguồn 1")
    hook_channels: Optional[List[SourceChannelConfig]] = Field(
        default=[], description="Danh sách các kênh nguồn Hook (Đoạn đầu)"
    )
    hook_duration_sec: float = Field(default=3.5, ge=1.0, le=30.0, description="Số giây lấy từ đầu video nguồn 1")
    body_skip_start_sec: float = Field(default=3.0, ge=0.0, le=60.0, description="Số giây bỏ qua ở đầu video nguồn 2")
    audio_mode: str = Field(default="sequential", description="Chế độ âm thanh: sequential | body_audio | hook_audio | bgm_override")
    aspect_ratio: str = Field(default="9:16", description="Tỷ lệ khung hình: '9:16' (Dọc) hoặc '16:9' (Ngang)")
    transition_duration_sec: float = Field(default=1.2, ge=0.4, le=5.0, description="Thời lượng chuyển cảnh xfade (giây) - mặc định 1.2s chuyển cảnh chậm, mượt mà")
    fallback_policy: str = Field(default="reuse_oldest", description="Chính sách khi hết Hook mới: reuse_oldest | wait | bypass")


class AutomationCampaignCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150, description="Tên chiến dịch Automation")
    source_channels: List[SourceChannelConfig] = Field(
        ..., min_length=1, description="Danh sách các kênh nguồn Douyin cần theo dõi"
    )
    target_pages: List[TargetPageConfig] = Field(
        default=[], description="Danh sách các Fanpage Facebook đích để đăng bài"
    )
    target_youtube_channels: List[TargetYouTubeChannelConfig] = Field(
        default=[], description="Danh sách các Kênh YouTube Shorts đích để đăng bài"
    )
    publish_to_youtube: bool = Field(
        default=False, description="Tự động xuất bản đồng thời lên Kênh YouTube"
    )
    youtube_video_type: Optional[str] = Field(
        default="shorts", description="Loại xuất bản YouTube: 'shorts' (Ngắn ≤ 60s) hoặc 'video' (Dài 16:9)"
    )
    fb_post_type: Optional[str] = Field(
        default="reel", description="Hình thức đăng Facebook: 'reel' (Thước phim) hoặc 'feed' (Bài viết)"
    )
    caption_template: str = Field(
        default="{title}", description="Mẫu tiêu đề/mô tả bài đăng (mặc định lấy {title} đã dịch)"
    )
    title_mode: Optional[str] = Field(
        default="auto_number",
        description="Chế độ tiêu đề: 'auto_number' (Bài đăng 1, 2...) hoặc 'original_title'",
    )
    custom_title_prefix: Optional[str] = Field(
        default="Bài đăng",
        description="Tiền tố tiêu đề khi dùng auto_number (VD: 'Bài đăng' -> 'Bài đăng 1')",
    )
    hashtags: Optional[str] = Field(
        default="#Douyin #Reels #Trending #VideoAI",
        description="Hashtags bổ sung gán vào cuối bài đăng",
    )
    auto_add_title_tag: bool = Field(
        default=True, description="Tự động tạo hashtag từ tên video đã dịch (vd: #TenVideo)"
    )
    crawl_interval_minutes: int = Field(
        default=30, ge=5, le=1440, description="Khoảng cách giữa các lần cào video (phút)"
    )
    only_today: bool = Field(
        default=True, description="Chỉ lấy video đăng trong ngày hôm nay"
    )
    max_video_age_hours: Optional[int] = Field(
        default=24, ge=0, le=720, description="Khoảng thời gian tối đa từ lúc video đăng đến khi cào (giờ), 0 là không giới hạn"
    )
    only_new_unprocessed: bool = Field(
        default=True, description="Chỉ lấy video mới nhất chưa từng có trong Database"
    )
    max_videos_per_crawl: int = Field(
        default=1, ge=1, le=5, description="Số lượng video mới tối đa xử lý mỗi lượt cào"
    )
    processing_mode: str = Field(
        default="both",
        description="Chế độ xử lý: 'both' (Vietsub + Thuyết minh), 'vietsub' (Chỉ Vietsub), 'dubbing' (Chỉ Thuyết minh), 'download_only' (Gốc sạch logo)",
    )
    voice_source: Optional[str] = Field(
        default="preset", description="Nguồn giọng: 'preset' (Edge-TTS) hoặc 'profile' (OmniVoice)"
    )
    voice_preset: Optional[str] = Field(
        default="vi-VN-NamMinhNeural", description="Giọng đọc AI thuyết minh nếu chọn chế độ dubbing"
    )
    voice_profile_id: Optional[str] = Field(
        default=None, description="ID hồ sơ giọng đã training của người dùng"
    )
    voice_name: Optional[str] = Field(
        default=None, description="Tên giọng đọc hiển thị"
    )
    remove_subtitles: bool = Field(
        default=True, description="Xóa sạch phụ đề cứng gốc tiếng Trung bằng AI Inpainting"
    )
    selected_bgm_ids: Optional[List[str]] = Field(
        default=[], description="Danh sách ID các bản ghi âm / bài BGM được chọn để random gán vào video ở Mô hình 2"
    )
    keep_original_audio: Optional[bool] = Field(
        default=False, description="Giữ nguyên 100% âm thanh gốc của video Douyin, không chèn/đè nhạc BGM"
    )
    bgm_volume: Optional[float] = Field(
        default=0.95, ge=0.0, le=2.0, description="Âm lượng nhạc nền BGM (0.0 - 2.0)"
    )
    dual_source: Optional[DualSourceConfig] = Field(
        default=None, description="Cấu hình chế độ ghép nối 2 nguồn (Hook + Body)"
    )
    is_active: bool = Field(default=True, description="Kích hoạt tự động hóa ngay sau khi tạo")


class AutomationCampaignUpdateRequest(BaseModel):
    name: Optional[str] = None
    source_channels: Optional[List[SourceChannelConfig]] = None
    target_pages: Optional[List[TargetPageConfig]] = None
    target_youtube_channels: Optional[List[TargetYouTubeChannelConfig]] = None
    caption_template: Optional[str] = None
    title_mode: Optional[str] = None
    custom_title_prefix: Optional[str] = None
    hashtags: Optional[str] = None
    auto_add_title_tag: Optional[bool] = None
    crawl_interval_minutes: Optional[int] = None
    only_today: Optional[bool] = None
    max_video_age_hours: Optional[int] = None
    only_new_unprocessed: Optional[bool] = None
    max_videos_per_crawl: Optional[int] = None
    processing_mode: Optional[str] = None
    voice_source: Optional[str] = None
    voice_preset: Optional[str] = None
    voice_profile_id: Optional[str] = None
    voice_name: Optional[str] = None
    remove_subtitles: Optional[bool] = None
    selected_bgm_ids: Optional[List[str]] = None
    keep_original_audio: Optional[bool] = None
    bgm_volume: Optional[float] = None
    dual_source: Optional[DualSourceConfig] = None
    publish_to_youtube: Optional[bool] = None
    youtube_video_type: Optional[str] = None
    fb_post_type: Optional[str] = None
    is_active: Optional[bool] = None


class PublishedPageResult(BaseModel):
    page_id: str
    page_name: str
    success: bool
    video_id: Optional[str] = None
    reel_url: Optional[str] = None
    error: Optional[str] = None


class PublishedYouTubeResult(BaseModel):
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    success: bool
    video_id: Optional[str] = None
    shorts_url: Optional[str] = None
    watch_url: Optional[str] = None
    video_type: Optional[str] = "shorts"
    error: Optional[str] = None


class AutomationCampaignResponse(BaseModel):
    id: str
    user_id: str
    name: str
    source_channels: List[SourceChannelConfig]
    target_pages: List[TargetPageConfig]
    target_youtube_channels: List[TargetYouTubeChannelConfig] = []
    publish_to_youtube: bool = False
    youtube_video_type: Optional[str] = "shorts"
    fb_post_type: Optional[str] = "reel"
    caption_template: str
    hashtags: Optional[str]
    auto_add_title_tag: bool
    crawl_interval_minutes: int
    only_today: bool
    max_video_age_hours: Optional[int] = 24
    only_new_unprocessed: bool
    max_videos_per_crawl: int
    processing_mode: str
    voice_source: Optional[str] = "preset"
    voice_preset: Optional[str] = None
    voice_profile_id: Optional[str] = None
    voice_name: Optional[str] = None
    remove_subtitles: bool
    selected_bgm_ids: Optional[List[str]] = []
    keep_original_audio: Optional[bool] = False
    bgm_volume: Optional[float] = 0.95
    dual_source: Optional[DualSourceConfig] = None
    is_active: bool
    status: str
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    total_posted: int = 0
    title_mode: Optional[str] = "auto_number"
    custom_title_prefix: Optional[str] = "Bài đăng"
    last_error: Optional[str] = None
    created_at: str
    updated_at: str


class AutomationCampaignListResponse(BaseModel):
    total: int
    campaigns: List[AutomationCampaignResponse]


class AutomationLogResponse(BaseModel):
    id: str
    campaign_id: str
    campaign_name: str
    user_id: str
    source_channel_name: str
    video_item_id: str
    video_url: Optional[str] = None
    video_original_title: str
    video_translated_title: str
    processing_mode: str
    caption: str
    status: str
    published_pages: List[PublishedPageResult]
    published_youtube_channels: Optional[List[PublishedYouTubeResult]] = None
    error: Optional[str] = None
    created_at: str


class AutomationLogListResponse(BaseModel):
    total: int
    logs: List[AutomationLogResponse]


class PostedVideoItemResponse(BaseModel):
    id: str
    user_id: str
    campaign_id: str
    campaign_name: str
    video_item_id: str
    video_url: str
    channel_name: str
    title_original: str
    title_translated: str
    processing_mode: str
    published_pages: List[PublishedPageResult]
    published_youtube_channels: Optional[List[PublishedYouTubeResult]] = None
    published_date: str
    created_at: str


class PostedVideoListResponse(BaseModel):
    total: int
    posted_videos: List[PostedVideoItemResponse]
