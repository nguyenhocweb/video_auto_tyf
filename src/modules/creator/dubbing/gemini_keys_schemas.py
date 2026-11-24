from typing import Optional, List
from pydantic import BaseModel, Field


class GeminiKeyCreateRequest(BaseModel):
    key: str = Field(..., min_length=15, description="API Key từ Google AI Studio (bắt đầu bằng AIzaSy...)")
    note: Optional[str] = Field("", max_length=100, description="Tên gợi nhớ (VD: Gmail chính, Kênh phụ 1)")
    model: Optional[str] = Field("gemini-2.5-flash", description="Model Gemini mặc định cho Key này")


class GeminiKeyUpdateModelRequest(BaseModel):
    model: str = Field(..., min_length=5, description="Tên model Gemini mới (VD: gemini-2.5-flash)")


class GeminiKeyTestRequest(BaseModel):
    key: Optional[str] = Field(None, description="API Key cần test (nếu truyền key_id thì có thể bỏ qua)")
    key_id: Optional[str] = Field(None, description="ID của Key đã lưu trong Database nếu muốn test key cũ")
    model: str = Field("gemini-2.5-flash", description="Model Gemini muốn kiểm tra")


class GeminiKeyTestResponse(BaseModel):
    success: bool
    model: str
    latency_ms: int
    test_output: Optional[str] = None
    error_code: Optional[int] = None
    message: str


class GeminiKeyResponse(BaseModel):
    id: str
    key_masked: str
    note: str = ""
    model: str = "gemini-2.5-flash"
    is_active: bool = True
    usage_count: int = 0
    error_count: int = 0
    last_used_at: Optional[str] = None
    created_at: str


class GeminiKeyListResponse(BaseModel):
    total: int
    items: List[GeminiKeyResponse]
