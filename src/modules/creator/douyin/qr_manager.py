import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable
from playwright.async_api import Browser, BrowserContext, Page
from src.core.utils.proactor_loop import ProactorLoopThread
from src.modules.creator.douyin.browser_controller import DouyinBrowserController

logger = logging.getLogger("douyin_qr_manager")


class DouyinQrManager:
    _instance: Optional["DouyinQrManager"] = None

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._on_confirmed_callback: Optional[Callable[[str, str, list, dict], Awaitable[None]]] = None
        self.proactor = ProactorLoopThread.get_instance()

    @classmethod
    def get_instance(cls) -> "DouyinQrManager":
        if cls._instance is None:
            cls._instance = DouyinQrManager()
        return cls._instance

    def set_on_confirmed_callback(self, callback: Callable[[str, str, list, dict], Awaitable[None]]):
        self._on_confirmed_callback = callback

    async def start_session(self, user_id: str) -> Dict[str, Any]:
        return await self.proactor.submit(self._start_session_impl(user_id))

    async def _start_session_impl(self, user_id: str) -> Dict[str, Any]:
        for sid, sess in list(self._sessions.items()):
            if sess.get("user_id") == str(user_id) and sess.get("status") in [
                "WAITING_FOR_SCAN", "SCANNED", "NEED_VERIFY"
            ]:
                await self._cancel_session_impl(sid)

        session_id = str(uuid.uuid4())
        logger.info(f"Khởi động phiên QR Douyin mới: {session_id} cho user: {user_id}")
        p, browser, context, page = await DouyinBrowserController.create_browser_session()

        qr_capture: Dict[str, Optional[str]] = {"src": None}
        qr_event = asyncio.Event()
        net_verify = {"needed": False, "mobile": None}

        async def _on_douyin_response(res):
            try:
                url = res.url
                if "get_qrcode" in url and res.status == 200:
                    data = (await res.json()).get("data", {})
                    if data.get("qrcode"):
                        qr_capture["src"] = f"data:image/png;base64,{data['qrcode']}"
                        qr_event.set()
                elif any(k in url for k in ["send_code", "sms/send", "passport/web/verify"]) and res.status == 200:
                    net_verify["needed"] = True
                    try:
                        data = (await res.json()).get("data") or {}
                        net_verify["mobile"] = data.get("mobile") or data.get("phone")
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", _on_douyin_response)
        try:
            qr_src = await DouyinBrowserController.open_login_modal_and_get_qr(page, qr_capture, qr_event)
        except Exception as exc:
            logger.error(f"Lỗi khi mở mã QR Douyin: {exc}")
            await DouyinBrowserController.cleanup_session(p, browser, context)
            raise RuntimeError(f"Không thể tải mã QR: {exc}")

        expires_at = time.time() + 120
        task = asyncio.create_task(self._poll_login_status(session_id))
        self._sessions[session_id] = {
            "session_id": session_id, "user_id": str(user_id), "qr_code_url": qr_src,
            "status": "WAITING_FOR_SCAN", "message": "Vui lòng mở app Douyin và quét mã QR.",
            "masked_mobile": None, "account_info": None, "expires_at": expires_at,
            "net_verify": net_verify, "playwright": p, "browser": browser,
            "context": context, "page": page, "task": task,
        }
        return {"session_id": session_id, "qr_code_url": qr_src, "expires_in": 120, "status": "WAITING_FOR_SCAN"}

    async def _poll_login_status(self, session_id: str):
        sess = self._sessions.get(session_id)
        if not sess:
            return
        context, page, p, browser, user_id = sess["context"], sess["page"], sess["playwright"], sess["browser"], sess["user_id"]
        net_verify = sess.get("net_verify", {})

        try:
            while time.time() < sess["expires_at"]:
                await asyncio.sleep(1.5)
                if session_id not in self._sessions:
                    break

                if await self._check_cookies_or_api(sess, context, p, browser, user_id):
                    return

                # Nhận diện OTP qua Network hoặc DOM
                is_need, mob = net_verify.get("needed", False), net_verify.get("mobile")
                if not is_need:
                    dom_need, dom_mob = await DouyinBrowserController.check_verify_needed(page)
                    if dom_need:
                        is_need, mob = True, dom_mob

                if is_need and sess["status"] != "NEED_VERIFY":
                    sess.update({"status": "NEED_VERIFY", "masked_mobile": mob, "message": "Yêu cầu mã xác minh OTP SMS."})
                    try:
                        import os
                        from src.modules.creator.douyin.browser_controller import get_scratch_dir
                        s1_path = os.path.join(get_scratch_dir(), "douyin_step1_scanned_otp.png")
                        await page.screenshot(path=s1_path)
                        logger.info(f"[CHỤP ẢNH MILESTONE 1] -> {s1_path}")
                    except Exception as e:
                        logger.warning(f"Không thể chụp ảnh milestone 1: {e}")
                elif not is_need and sess["status"] == "WAITING_FOR_SCAN":
                    if await DouyinBrowserController.check_is_scanned(page):
                        sess.update({"status": "SCANNED", "message": "Đã quét mã! Đang xử lý đăng nhập..."})

            sess.update({"status": "EXPIRED", "message": "Mã QR đã hết hạn."})
            await DouyinBrowserController.cleanup_session(p, browser, context)
        except asyncio.CancelledError:
            sess["status"] = "CANCELLED"
            await DouyinBrowserController.cleanup_session(p, browser, context)
        except Exception as exc:
            logger.error(f"Lỗi polling QR session {session_id}: {exc}")
            sess.update({"status": "FAILED", "message": str(exc)})
            await DouyinBrowserController.cleanup_session(p, browser, context)

    async def _check_cookies_or_api(self, sess, context, p, browser, user_id) -> bool:
        """Kiểm tra xem Douyin đã cấp phiên đăng nhập hợp lệ chưa."""
        try:
            res = await context.request.get("https://www.douyin.com/passport/web/account/info/", timeout=2000)
            if res.status == 200:
                acc_data = (await res.json()).get("data") or {}
                if acc_data.get("user_id"):
                    await self._handle_success(sess, context, p, browser, user_id, acc_data)
                    return True
        except Exception:
            pass

        cookies = await context.cookies()
        names = {c["name"] for c in cookies}
        if any(k in names for k in ["sessionid", "sessionid_ss", "sid_guard", "sid_tt"]):
            acc_info = {"name": "Douyin Creator", "user_id": ""}
            for c in cookies:
                if c["name"] in ["uid_tt", "uid_tt_ss"]:
                    acc_info["user_id"] = c["value"]
            await self._handle_success(sess, context, p, browser, user_id, acc_info)
            return True
        return False

    async def _handle_success(self, sess, context, p, browser, user_id, acc_info):
        cookies = await context.cookies()
        cookies_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        sess.update({"status": "CONFIRMED", "message": "Đăng nhập Douyin thành công!", "account_info": acc_info})
        if self._on_confirmed_callback:
            try:
                await self._on_confirmed_callback(user_id, cookies_str, cookies, acc_info)
            except Exception as cb_err:
                logger.error(f"Lỗi callback: {cb_err}")
        await asyncio.sleep(1.5)
        await DouyinBrowserController.cleanup_session(p, browser, context)

    async def submit_code(self, session_id: str, code: str) -> bool:
        return await self.proactor.submit(self._submit_code_impl(session_id, code))

    async def _submit_code_impl(self, session_id: str, code: str) -> bool:
        sess = self._sessions.get(session_id)
        if not sess:
            raise ValueError("Phiên xác thực không tồn tại hoặc đã hết hạn.")
        success = await DouyinBrowserController.submit_otp_code(sess["page"], code)
        if success:
            context, p, browser, user_id = sess["context"], sess["playwright"], sess["browser"], sess["user_id"]
            for _ in range(6):
                await asyncio.sleep(1.0)
                if await self._check_cookies_or_api(sess, context, p, browser, user_id):
                    return True
        return success

    async def resend_code(self, session_id: str) -> bool:
        return await self.proactor.submit(self._resend_code_impl(session_id))

    async def _resend_code_impl(self, session_id: str) -> bool:
        sess = self._sessions.get(session_id)
        if not sess:
            raise ValueError("Phiên xác thực không tồn tại hoặc đã hết hạn.")
        return await DouyinBrowserController.resend_otp_code(sess["page"])

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        sess = self._sessions.get(session_id)
        if not sess:
            return {"session_id": session_id, "status": "EXPIRED", "message": "Phiên không tồn tại.", "masked_mobile": None, "account_info": None}
        return {"session_id": session_id, "status": sess.get("status", "WAITING_FOR_SCAN"), "message": sess.get("message"), "masked_mobile": sess.get("masked_mobile"), "account_info": sess.get("account_info")}

    async def cancel_session(self, session_id: str) -> bool:
        return await self.proactor.submit(self._cancel_session_impl(session_id))

    async def _cancel_session_impl(self, session_id: str) -> bool:
        sess = self._sessions.pop(session_id, None)
        if not sess:
            return False
        sess["status"] = "CANCELLED"
        task = sess.get("task")
        if isinstance(task, asyncio.Task) and not task.done():
            task.cancel()
        await DouyinBrowserController.cleanup_session(sess.get("playwright"), sess.get("browser"), sess.get("context"))
        return True
