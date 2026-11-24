from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class SceneItem(BaseModel):
    scene_idx: int = Field(..., description="Thu tu canh quay")
    narration: str = Field(..., description="Loi dan thuyet minh tieng Viet")
    prompt_en: str = Field(..., description="Cau prompt ve anh bang tieng Anh")
    estimated_duration: Optional[float] = Field(default=4.0, description="Thoi luong du kien (s)")
    image_url: Optional[str] = Field(default=None, description="URL anh da tai len cho canh nay")
    image_path: Optional[str] = Field(default=None, description="Duong dan tep anh noi bo tren may chu")

class ScriptGenerateRequest(BaseModel):
    topic: str = Field(..., description="Chu de hoac y tuong cau chuyen")
    art_style: str = Field(
        default="stickman",
        description="Phong cach hoi hoa & nhan vat (stickman, modern_vector, anime, comic_webtoon, doodle_sketch)",
    )
    genre: str = Field(
        default="knowledge_sharing",
        description="The loai noi dung & giong ke (knowledge_sharing, horror_mystery, motivation, daily_comedy)",
    )
    style: Optional[str] = Field(default=None, description="Tham so cu tuong thich nguoc")
    scene_count: int = Field(default=8, ge=3, le=60, description="So luong canh quay (3 - 60)")
    gemini_api_key: Optional[str] = Field(default=None, description="Khóa Gemini API tùy chọn")

class ScriptGenerateResponse(BaseModel):
    success: bool = True
    topic: str
    art_style: str = "stickman"
    art_style_name: str = "Stickman Người Que"
    genre: str = "knowledge_sharing"
    genre_name: str = "Kể Chuyện & Chia Sẻ Kiến Thức"
    style: str = "stickman"
    style_name: str = "Stickman Người Que"
    scenes: List[SceneItem]
    message: str = "Sinh kich ban va prompt thanh cong"

class RenderStoryboardRequest(BaseModel):
    job_id: Optional[str] = Field(default=None, description="ID cua phien lam viec")
    topic: str = Field(default="Câu chuyện AI", description="Tieu de cau chuyen")
    scenes: List[SceneItem] = Field(..., description="Danh sach cac canh da gan anh va loi thoai")
    voice_name: str = Field(default="vi-VN-NamMinhNeural", description="Giong doc AI (vi-VN-NamMinhNeural hoac vi-VN-HoaiMyNeural)")

class RenderStoryboardResponse(BaseModel):
    success: bool = True
    job_id: str
    video_url: str
    video_path: Optional[str] = None
    duration: float
    scenes_count: int
    message: str = "Render video hoan tat thanh cong"

class StoryboardPublishRequest(BaseModel):
    job_id: str = Field(..., description="ID phiên render storyboard")
    platform: str = Field(default="youtube", description="Nền tảng đăng: youtube | facebook | tiktok")
    channel_id: Optional[str] = Field(None, description="ID Kênh YouTube hoặc Page Facebook đích")
    title: str = Field(..., max_length=150, description="Tên / Tiêu đề video")
    hashtags: Optional[str] = Field(default="", description="Chuỗi hashtag kèm theo")
    description: Optional[str] = Field(default="", description="Mô tả nội dung chi tiết")
    privacy_status: Optional[str] = Field(default="public", description="Trạng thái hiển thị (public/unlisted/private)")

class StoryboardPublishResponse(BaseModel):
    success: bool = True
    platform: str
    channel_title: Optional[str] = None
    post_url: Optional[str] = None
    title: str
    message: str = "Đăng video thành công"

class CleanWatermarkRequest(BaseModel):
    job_id: str = Field(..., description="ID phien lam viec")
    scene_idx: int = Field(..., description="So thu tu phan canh can xoa logo")
    watermark_type: str = Field(default="gemini", description="Loai watermark: gemini hoac custom")
    custom_box: Optional[Dict[str, float]] = Field(default=None, description="Toa do hop tuy chinh neu co")

class CleanWatermarkResponse(BaseModel):
    success: bool = True
    scene_idx: int
    url: str
    path: str
    detected: bool
    message: str = "Đã khử sạch watermark thành công"

class BatchCleanRequest(BaseModel):
    job_id: str = Field(..., description="ID phien lam viec")
    scene_indices: Optional[List[int]] = Field(default=None, description="Danh sach scene can lam sach (None la tat ca)")

class BatchCleanResponse(BaseModel):
    success: bool = True
    cleaned_count: int
    scenes: List[Dict[str, Any]]
    message: str = "Đã làm sạch watermark hàng loạt thành công"

class VoiceOptionItem(BaseModel):
    id: str
    name: str
    gender: Optional[str] = "NEUTRAL"
    type: str = "preset"  # "preset" hoặc "trained"
    is_finetuned: Optional[bool] = False

class VoiceOptionsResponse(BaseModel):
    success: bool = True
    voices: List[VoiceOptionItem]

