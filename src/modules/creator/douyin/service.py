import logging
from typing import Optional, Dict, Any
from src.modules.creator.douyin.repository import DouyinMongoRepository
from src.modules.creator.douyin.qr_manager import DouyinQrManager
from src.modules.creator.douyin.schemas import (
    DouyinSessionStatusResponse,
    DouyinQrStartResponse,
    DouyinQrStatusResponse,
)

logger = logging.getLogger("douyin_service")


class DouyinSessionService:
    _cached_active_cookie: Optional[str] = None

    def __init__(self):
        self.repository = DouyinMongoRepository()
        self.qr_manager = DouyinQrManager.get_instance()
        # Đăng ký callback khi QR xác nhận thành công
        self.qr_manager.set_on_confirmed_callback(self._on_qr_confirmed)

    async def _on_qr_confirmed(
        self, user_id: str, cookies_str: str, cookies_list: list, account_info: dict
    ):
        """Callback lưu phiên đăng nhập Douyin vào Database và cập nhật cache cookie."""
        try:
            await self.repository.save_session(
                user_id=user_id,
                cookies_str=cookies_str,
                cookies_list=cookies_list,
                account_info=account_info,
            )
            DouyinSessionService._cached_active_cookie = cookies_str
            logger.info(f"Đã cập nhật Cookie Douyin mới nhất vào cache cho user={user_id}!")
        except Exception as exc:
            logger.error(f"Lỗi khi lưu phiên Douyin vào database: {exc}")

    async def get_status(self, user_id: str) -> DouyinSessionStatusResponse:
        """Kiểm tra trạng thái liên kết tài khoản Douyin của người dùng."""
        session = await self.repository.get_active_session(user_id=user_id)
        if not session or not session.get("is_active"):
            return DouyinSessionStatusResponse(is_connected=False)

        # Cập nhật cache cookie nếu có session hợp lệ
        if session.get("cookies_str"):
            DouyinSessionService._cached_active_cookie = session.get("cookies_str")

        return DouyinSessionStatusResponse(
            is_connected=True,
            nickname=session.get("nickname"),
            avatar_url=session.get("avatar_url"),
            uid=session.get("uid"),
            sec_uid=session.get("sec_uid"),
            last_connected_at=session.get("last_connected_at"),
            expires_at=session.get("expires_at"),
        )

    async def start_qr(self, user_id: str) -> DouyinQrStartResponse:
        """Bắt đầu tiến trình tạo mã QR đăng nhập Douyin."""
        res = await self.qr_manager.start_session(user_id=user_id)
        return DouyinQrStartResponse(
            session_id=res["session_id"],
            qr_code_url=res["qr_code_url"],
            expires_in=res.get("expires_in", 120),
            status=res.get("status", "WAITING_FOR_SCAN"),
        )

    def get_qr_status(self, session_id: str) -> DouyinQrStatusResponse:
        """Kiểm tra trạng thái quét mã QR theo session_id."""
        res = self.qr_manager.get_session_status(session_id=session_id)
        return DouyinQrStatusResponse(
            session_id=session_id,
            status=res["status"],
            message=res.get("message"),
            masked_mobile=res.get("masked_mobile"),
            account_info=res.get("account_info"),
        )

    async def submit_otp_code(self, session_id: str, code: str) -> bool:
        """Nhập mã OTP 2FA SMS vào Douyin."""
        return await self.qr_manager.submit_code(session_id=session_id, code=code)

    async def resend_otp_code(self, session_id: str) -> bool:
        """Yêu cầu gửi lại mã OTP SMS trên Douyin."""
        return await self.qr_manager.resend_code(session_id=session_id)

    async def cancel_qr(self, session_id: str) -> bool:
        """Hủy phiên quét mã QR."""
        return await self.qr_manager.cancel_session(session_id=session_id)

    async def logout(self, user_id: str) -> bool:
        """Đăng xuất và hủy phiên làm việc Douyin của người dùng."""
        success = await self.repository.deactivate_session(user_id=user_id)
        if success:
            DouyinSessionService._cached_active_cookie = None
        return success

    @classmethod
    def get_cached_cookie(cls) -> Optional[str]:
        """Lấy Cookie Douyin đang active trong bộ nhớ cache server."""
        return cls._cached_active_cookie
