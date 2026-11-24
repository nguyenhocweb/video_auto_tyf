from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class DouyinSessionStatusResponse(BaseModel):
    is_connected: bool = Field(..., description="Trạng thái tài khoản Douyin đã kết nối hay chưa")
    nickname: Optional[str] = Field(None, description="Tên hiển thị của tài khoản Douyin")
    avatar_url: Optional[str] = Field(None, description="Ảnh đại diện của tài khoản Douyin")
    uid: Optional[str] = Field(None, description="Mã định danh User ID trên Douyin")
    sec_uid: Optional[str] = Field(None, description="Mã bảo mật Sec UID trên Douyin")
    last_connected_at: Optional[str] = Field(None, description="Thời điểm kết nối/cập nhật gần nhất (ISO VN UTC+7)")
    expires_at: Optional[str] = Field(None, description="Thời điểm dự kiến hết hạn Cookie")


class DouyinQrStartResponse(BaseModel):
    session_id: str = Field(..., description="ID phiên quét mã QR")
    qr_code_url: str = Field(..., description="Ảnh QR code dạng data:image/png;base64,...")
    expires_in: int = Field(120, description="Thời gian sống của mã QR tính bằng giây")
    status: str = Field("WAITING_FOR_SCAN", description="Trạng thái ban đầu của mã QR")


class DouyinQrStatusResponse(BaseModel):
    session_id: str = Field(..., description="ID phiên quét mã QR")
    status: str = Field(..., description="WAITING_FOR_SCAN | SCANNED | NEED_VERIFY | CONFIRMED | EXPIRED | FAILED | CANCELLED")
    message: Optional[str] = Field(None, description="Thông báo chi tiết trạng thái")
    masked_mobile: Optional[str] = Field(None, description="Số điện thoại che dấu nhận mã OTP nếu cần xác thực")
    account_info: Optional[Dict[str, Any]] = Field(None, description="Thông tin tài khoản nhận được khi đăng nhập thành công")


class DouyinSubmitCodeRequest(BaseModel):
    session_id: str = Field(..., description="ID phiên quét mã QR đang chờ xác minh")
    code: str = Field(..., min_length=4, max_length=8, description="Mã OTP / SMS nhận được trên điện thoại")


class DouyinSendCodeRequest(BaseModel):
    session_id: str = Field(..., description="ID phiên quét mã QR cần gửi lại mã SMS")
