from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ImageInspectRequest(BaseModel):
    """Payload gửi ảnh dạng Base64 hoặc URL để phân tích độ HOT và vi phạm."""
    image_base64: Optional[str] = Field(None, description="Chuỗi ảnh Base64 (data:image/...)")
    image_url: Optional[str] = Field(None, description="URL ảnh cần phân tích")


class ImageInspectResponse(BaseModel):
    """Kết quả phân tích ảnh bìa/thumbnail."""
    overall_viral_score: int = Field(..., ge=0, le=100, description="Điểm tiềm năng viral 0-100")
    rating: str = Field(..., description="Đánh giá tổng quan (Rất Hot, Khá Tốt...)")
    face_analysis: Dict[str, Any] = Field(default_factory=dict)
    visual_analysis: Dict[str, Any] = Field(default_factory=dict)
    text_analysis: Dict[str, Any] = Field(default_factory=dict)
    skin_safety: Dict[str, Any] = Field(default_factory=dict)
    actionable_advice: List[str] = Field(default_factory=list)


class TextPolicyInspectRequest(BaseModel):
    """Payload gửi kịch bản/phụ đề để quét từ ngữ vi phạm."""
    text: str = Field(..., min_length=1, description="Đoạn văn bản cần kiểm tra")


class TextPolicyInspectResponse(BaseModel):
    """Kết quả quét từ cấm và gợi ý né gậy."""
    is_safe: bool
    safety_score: int = Field(..., ge=0, le=100)
    total_violations: int
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    rewritten_text: str
    summary: str


class VideoInspectRequest(BaseModel):
    """Payload thẩm định video."""
    job_id: Optional[str] = Field(None, description="ID tác vụ dubbing đã có trong hệ thống")
    video_url: Optional[str] = Field(None, description="URL file video trực tiếp")


class VideoInspectResponse(BaseModel):
    """Kết quả thẩm định nhịp độ và vi phạm của video."""
    composite_viral_score: int = Field(..., ge=0, le=100)
    pacing: Dict[str, Any] = Field(default_factory=dict)
    policy: Dict[str, Any] = Field(default_factory=dict)
    actionable_advice: List[str] = Field(default_factory=list)


class InspectorHistoryItem(BaseModel):
    """Bản ghi lịch sử thẩm định."""
    id: str
    type: str  # "image" hoặc "video"
    score: int
    summary: str
    created_at: str

