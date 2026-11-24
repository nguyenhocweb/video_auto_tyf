import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.douyin.schemas import (
    DouyinSessionStatusResponse,
    DouyinQrStartResponse,
    DouyinQrStatusResponse,
    DouyinSubmitCodeRequest,
    DouyinSendCodeRequest,
)
from src.modules.creator.douyin.service import DouyinSessionService

logger = logging.getLogger("douyin_router")

router = APIRouter(prefix="/douyin/session", tags=["Creator - Douyin Account Session"])
service = DouyinSessionService()


def _get_user_id(user: Any) -> str:
    """Trích xuất User ID an toàn từ dict MongoDB hoặc Object."""
    if isinstance(user, dict):
        return str(user.get("id") or user.get("_id") or "")
    return str(getattr(user, "id", ""))


@router.get("/status", response_model=DouyinSessionStatusResponse)
async def get_douyin_status(current_user=Depends(get_current_user)):
    """Lấy trạng thái kết nối tài khoản Douyin hiện tại của người dùng."""
    try:
        user_id = _get_user_id(current_user)
        return await service.get_status(user_id=user_id)
    except Exception as exc:
        logger.error(f"Lỗi khi kiểm tra trạng thái Douyin: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/qr/start", response_model=DouyinQrStartResponse)
async def start_qr_login(current_user=Depends(get_current_user)):
    """Khởi tạo phiên quét mã QR đăng nhập Douyin."""
    try:
        user_id = _get_user_id(current_user)
        return await service.start_qr(user_id=user_id)
    except Exception as exc:
        logger.error(f"Lỗi khi khởi tạo mã QR Douyin: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/qr/status/{session_id}", response_model=DouyinQrStatusResponse)
async def get_qr_status(session_id: str, current_user=Depends(get_current_user)):
    """Kiểm tra trạng thái quét mã QR theo session_id."""
    try:
        return service.get_qr_status(session_id=session_id)
    except Exception as exc:
        logger.error(f"Lỗi khi kiểm tra trạng thái QR: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/qr/submit-code")
async def submit_otp_code(payload: DouyinSubmitCodeRequest, current_user=Depends(get_current_user)):
    """Nhập mã xác minh SMS / OTP gửi về điện thoại để hoàn tất đăng nhập Douyin."""
    try:
        success = await service.submit_otp_code(session_id=payload.session_id, code=payload.code)
        return {"success": success, "message": "Đã gửi mã xác minh thành công"}
    except Exception as exc:
        logger.error(f"Lỗi khi nhập mã OTP Douyin: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/qr/send-code")
async def resend_otp_code(payload: DouyinSendCodeRequest, current_user=Depends(get_current_user)):
    """Yêu cầu Douyin gửi lại mã xác minh SMS về số điện thoại."""
    try:
        success = await service.resend_otp_code(session_id=payload.session_id)
        return {"success": success, "message": "Đã bấm gửi lại mã xác minh"}
    except Exception as exc:
        logger.error(f"Lỗi khi gửi lại mã OTP Douyin: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/qr/cancel/{session_id}")
async def cancel_qr_login(session_id: str, current_user=Depends(get_current_user)):
    """Hủy phiên quét mã QR."""
    try:
        cancelled = await service.cancel_qr(session_id=session_id)
        return {"success": cancelled, "message": "Đã hủy phiên quét mã QR"}
    except Exception as exc:
        logger.error(f"Lỗi khi hủy phiên QR: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/logout")
async def logout_douyin(current_user=Depends(get_current_user)):
    """Đăng xuất và hủy liên kết tài khoản Douyin."""
    try:
        user_id = _get_user_id(current_user)
        success = await service.logout(user_id=user_id)
        return {"success": success, "message": "Đã hủy kết nối tài khoản Douyin"}
    except Exception as exc:
        logger.error(f"Lỗi khi đăng xuất Douyin: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
