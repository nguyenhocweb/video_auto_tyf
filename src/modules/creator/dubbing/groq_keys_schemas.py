from typing import Optional, List
from pydantic import BaseModel, Field


class GroqKeyCreateRequest(BaseModel):
    key: str = Field(..., min_length=15, description="API Key từ Groq Cloud (bắt đầu bằng gsk_...)")
    note: Optional[str] = Field("", max_length=100, description="Tên gợi nhớ (VD: Groq Gmail 1, Key dự phòng)")
    model: Optional[str] = Field("qwen/qwen3.8-27b", description="Model Groq mặc định cho Key này")


class GroqKeyUpdateModelRequest(BaseModel):
    model: str = Field(..., min_length=3, description="Tên model Groq mới (VD: qwen/qwen3.8-27b)")


class GroqKeyTestRequest(BaseModel):
    key: Optional[str] = Field(None, description="API Key cần test (nếu truyền key_id thì có thể bỏ qua)")
    key_id: Optional[str] = Field(None, description="ID của Key đã lưu trong Database nếu muốn test key cũ")
    model: str = Field("qwen/qwen3.8-27b", description="Model Groq muốn kiểm tra")


class GroqKeyTestResponse(BaseModel):
    success: bool
    model: str
    latency_ms: int
    test_output: Optional[str] = None
    error_code: Optional[int] = None
    message: str


class GroqKeyResponse(BaseModel):
    id: str
    key_masked: str
    note: str = ""
    model: str = "qwen/qwen3.8-27b"
    is_active: bool = True
    usage_count: int = 0
    error_count: int = 0
    last_used_at: Optional[str] = None
    created_at: str


class GroqKeyListResponse(BaseModel):
    total: int
    items: List[GroqKeyResponse]

