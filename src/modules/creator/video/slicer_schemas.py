from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class SlotRequirement(BaseModel):
    id: str = Field(default="1", description="Ma dinh danh slot (VD: slot_1)")
    type: str = Field(default="image", description="Loai slot: 'image' hoac 'video'")
    duration: Optional[float] = Field(default=2.0, description="Thoi luong (s) neu slot la video")
    description: Optional[str] = Field(default="", description="Mo ta slot (VD: Canh can mat, canh tong the)")

class SliceVideoToTemplateRequest(BaseModel):
    video_url: Optional[str] = Field(default=None, description="URL video Douyin / CDN")
    video_path: Optional[str] = Field(default=None, description="Duong dan video noi bo tren may chu")
    slots: List[SlotRequirement] = Field(default_factory=list, description="Danh sach slots yeu cau cua Mau")

class SlicedAssetResponse(BaseModel):
    slot_id: str
    index: int
    type: str
    file_name: str
    download_url: str
    timestamp: float
    duration: Optional[float] = None

class SliceVideoToTemplateResponse(BaseModel):
    success: bool = True
    job_id: str
    video_info: Dict[str, Any]
    detected_scenes_count: int
    total_slots: int
    assets: List[SlicedAssetResponse]
    zip_download_url: str
    message: str = "Giai phau video thanh bo tai nguyen mau thanh cong"

