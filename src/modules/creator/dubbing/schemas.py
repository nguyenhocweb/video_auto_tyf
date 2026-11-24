import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class SubtitleSegmentSchema(BaseModel):
    id: int = Field(..., description="Thứ tự đoạn thoại")
    start: float = Field(..., description="Thời điểm bắt đầu (giây)")
    end: float = Field(..., description="Thời điểm kết thúc (giây)")
    duration: float = Field(..., description="Độ dài đoạn thoại (giây)")
    text_origin: str = Field(..., description="Nội dung lời thoại gốc (tiếng Trung)")
    text_translated: str = Field(default="", description="Nội dung đã dịch (tiếng Việt)")


class DubbingTranscribeRequest(BaseModel):
    video_url: str = Field(..., description="Đường dẫn file video hoặc URL video cần bóc tách lời thoại")
    language: str = Field(default="zh", description="Ngôn ngữ gốc của video (zh, en, auto)")
    model_size: str = Field(default="base", description="Kích thước mô hình Faster-Whisper (tiny, base, small)")


class DubbingTranscribeResponse(BaseModel):
    video_url: str
    total_segments: int
    duration_total: float
    segments: List[SubtitleSegmentSchema]


class DubbingTranslateRequest(BaseModel):
    segments: List[SubtitleSegmentSchema] = Field(..., description="Danh sách các đoạn cần dịch")
    source_lang: str = Field(default="zh-CN", description="Ngôn ngữ nguồn")
    target_lang: str = Field(default="vi", description="Ngôn ngữ đích")


class DubbingTranslateResponse(BaseModel):
    segments: List[SubtitleSegmentSchema]


class DubbingRenderRequest(BaseModel):
    video_url: str = Field(..., description="URL hoặc đường dẫn file video gốc")
    segments: List[SubtitleSegmentSchema] = Field(..., description="Danh sách phụ đề đã được dịch/chỉnh sửa")
    mode: str = Field(default="both", description="Chế độ xử lý: 'vietsub' | 'dubbing' | 'both'")
    voice_source: str = Field(default="preset", description="Nguồn giọng: 'preset' (Edge-TTS) hoặc 'profile' (OmniVoice)")
    voice_preset: str = Field(default="vi-VN-NamMinhNeural", description="Giọng mẫu: vi-VN-NamMinhNeural hoặc vi-VN-HoaiMyNeural")
    voice_profile_id: Optional[str] = Field(default=None, description="ID hồ sơ giọng tùy chỉnh của người dùng (nếu có)")
    bgm_volume: float = Field(default=0.18, description="Âm lượng nhạc nền/thoại gốc (0.0 đến 1.0)")
    voice_volume: float = Field(default=1.0, description="Âm lượng giọng thuyết minh tiếng Việt (0.5 đến 2.0)")
    remove_subtitles: bool = Field(default=True, description="Xóa sạch phụ đề cứng tiếng Trung gốc bằng AI Inpainting")
    font_size: int = Field(default=31, description="Cỡ chữ phụ đề ASS (20 đến 45, mặc định 31)")


class AutoDubbingFromUrlRequest(BaseModel):
    url: str = Field(..., description="Đường link video Douyin / TikTok hoặc URL video MP4")
    mode: str = Field(default="both", description="Chế độ: 'both' | 'vietsub' | 'dubbing' | 'download_only'")
    voice_source: str = Field(default="preset", description="Nguồn giọng: 'preset' hoặc 'profile'")
    voice_preset: str = Field(default="vi-VN-NamMinhNeural", description="Tên giọng đọc mẫu")
    voice_profile_id: Optional[str] = Field(default=None, description="ID hồ sơ giọng cá nhân")
    voice_name: Optional[str] = Field(default=None, description="Tên giọng đọc hiển thị")
    remove_subtitles: bool = Field(default=True, description="Tự động xóa phụ đề cứng gốc")
    bgm_volume: float = Field(default=0.18, description="Âm lượng nhạc nền")
    voice_volume: float = Field(default=1.0, description="Âm lượng thuyết minh")
    font_size: int = Field(default=31, description="Cỡ chữ phụ đề ASS (20 đến 45, mặc định 31)")


class DubbingCleanVideoRequest(BaseModel):
    video_url: str = Field(..., description="URL hoặc đường dẫn video cần xóa phụ đề cứng")
    ymin_ratio: float = Field(default=0.70, description="Tọa độ Y bắt đầu vùng phụ đề (0.0 đến 1.0)")
    ymax_ratio: float = Field(default=0.92, description="Tọa độ Y kết thúc vùng phụ đề (0.0 đến 1.0)")


class DubbingJobResponse(BaseModel):
    id: str
    user_id: str
    title: Optional[str] = None
    cover_url: Optional[str] = None
    source_url: Optional[str] = None
    video_url: Optional[str] = None
    mode: str
    status: str
    progress_step: Optional[str] = None
    progress_percent: Optional[int] = 0
    voice_source: Optional[str] = "preset"
    voice_preset: Optional[str] = None
    voice_profile_id: Optional[str] = None
    voice_name: Optional[str] = None
    bgm_volume: Optional[float] = 0.18
    voice_volume: Optional[float] = 1.0
    segments_count: Optional[int] = 0
    output_video_url: Optional[str] = None
    cloudinary_url: Optional[str] = None
    subtitle_srt_url: Optional[str] = None
    subtitle_ass_url: Optional[str] = None
    error_message: Optional[str] = None
    remove_subtitles: Optional[bool] = True
    font_size: Optional[int] = 31
    created_at: Union[str, datetime.datetime]
    updated_at: Optional[Union[str, datetime.datetime]] = None


class TranslateContentRequest(BaseModel):
    title: Optional[str] = Field(default="", description="Tiêu đề cần dịch")
    caption: Optional[str] = Field(default="", description="Mô tả / nội dung cần dịch")


class TranslateContentResponse(BaseModel):
    title: str = Field(default="", description="Tiêu đề đã dịch")
    caption: str = Field(default="", description="Mô tả đã dịch")

