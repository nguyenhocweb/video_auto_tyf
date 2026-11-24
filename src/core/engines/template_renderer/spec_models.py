"""Mô hình dữ liệu đặc tả cấu hình Template Video (Pydantic v2).
Đảm bảo tách biệt tuyệt đối giữa Code Engine và Data Specs.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ResolutionSpec(BaseModel):
    """Quy chuẩn kích thước và tốc độ khung hình của video xuất xưởng."""
    width: int = Field(default=1080, description="Chiều rộng pixel (mặc định 1080 cho 9:16)")
    height: int = Field(default=1920, description="Chiều cao pixel (mặc định 1920 cho 9:16)")
    fps: int = Field(default=30, description="Tốc độ khung hình (30 hoặc 60fps)")


class SlotSpec(BaseModel):
    """Đặc tả từng slot input người dùng cần cung cấp (Video, Ảnh hoặc Audio)."""
    slot_id: int = Field(..., description="ID định danh slot (1, 2, 3...)")
    slot_type: Literal["video", "image", "audio"] = Field(..., description="Loại media yêu cầu")
    title: str = Field(..., description="Tiêu đề hiển thị trực quan cho slot")
    description: str = Field("", description="Hướng dẫn gợi ý nội dung nạp vào slot")
    start_time: float = Field(0.0, description="Thời điểm bắt đầu xuất hiện trong video (giây)")
    duration: float = Field(..., description="Thời lượng phân bổ cho slot (giây)")
    required: bool = Field(True, description="Bắt buộc phải có file hay không")


class EffectSpec(BaseModel):
    """Đặc tả hiệu ứng đồ họa hoặc shader áp dụng lên slot."""
    name: str = Field(..., description="Tên hiệu ứng: camera_shake, white_flash, rgb_split, ken_burns, blur_bg")
    trigger: Literal["beat_sync", "transition", "continuous", "time_window"] = Field(
        default="continuous", description="Điều kiện kích hoạt hiệu ứng"
    )
    start_time: Optional[float] = Field(None, description="Thời điểm bắt đầu (nếu là time_window)")
    duration: Optional[float] = Field(None, description="Thời lượng kéo dài hiệu ứng (giây)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Các tham số tinh chỉnh độ mạnh, chu kỳ")


class ExportSettings(BaseModel):
    """Cấu hình render phần cứng (GPU NVENC / CPU)."""
    encoder: Literal["h264_nvenc", "libx264"] = Field(default="h264_nvenc", description="Bộ mã hóa video")
    preset: str = Field(default="p4", description="Preset mã hóa (p4 cho NVENC, veryfast cho CPU)")
    cq: int = Field(default=23, description="Chất lượng nén (Constant Quality, càng nhỏ càng nét)")
    max_vram_mb: int = Field(default=2048, description="Giới hạn an toàn VRAM (tránh tràn 4GB của RTX 3050)")


class TemplateSpec(BaseModel):
    """Đặc tả hoàn chỉnh của một mẫu video."""
    template_id: str = Field(..., description="Mã định danh duy nhất của mẫu (ví dụ: t01_beat_drop)")
    name: str = Field(..., description="Tên hiển thị của mẫu")
    description: str = Field("", description="Mô tả phong cách và cấu trúc của mẫu")
    category: str = Field(default="capcut_trending", description="Chuyên mục mẫu")
    version: str = Field(default="1.0.0", description="Phiên bản mẫu")
    total_duration: float = Field(..., description="Tổng thời lượng video xuất ra (giây)")
    resolution: ResolutionSpec = Field(default_factory=ResolutionSpec)
    slots: List[SlotSpec] = Field(..., description="Danh sách các slot nạp media")
    effects: List[EffectSpec] = Field(default_factory=list, description="Danh sách hiệu ứng")
    export_settings: ExportSettings = Field(default_factory=ExportSettings)
    default_bgm: Optional[str] = Field(None, description="Đường dẫn tương đối đến file nhạc nền mẫu")
