import asyncio
import os
import re
import logging
from typing import Dict, Any, Optional, Tuple, List, Union
from playwright.async_api import Browser, BrowserContext, Page, Frame, Locator, async_playwright
from src.core.config import settings

logger = logging.getLogger("douyin_browser_controller")


def get_scratch_dir() -> str:
    """Trả về đường dẫn tuyệt đối đến thư mục be/tests/scratch/."""
    d = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../tests/scratch"))
    os.makedirs(d, exist_ok=True)
    return d


class DouyinBrowserController:
    """Điều khiển trình duyệt Playwright cho Douyin: tối ưu tốc độ, lọc tài nguyên và xử lý 2FA OTP."""

    @staticmethod
    async def create_browser_session() -> Tuple[Any, Browser, BrowserContext, Page]:
        """Khởi động browser context với các cờ stealth và chặn video streams làm nghẽn mạng."""
        p = await async_playwright().start()
        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1280,720",
            "--disable-gpu",
        ]
        try:
            browser: Browser = await p.chromium.launch(
                channel="chrome", headless=settings.PLAYWRIGHT_HEADLESS, args=launch_args
            )
        except Exception:
            browser = await p.chromium.launch(
                headless=settings.PLAYWRIGHT_HEADLESS, args=launch_args
            )
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 720}, locale="zh-CN",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        async def _block_heavy_media(route):
            url = route.request.url.lower()
            if any(ext in url for ext in [".mp4", ".m4s", ".ts", "bytevcloud.com", "douyinvod.com"]):
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", _block_heavy_media)
        page: Page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(document, 'visibilityState', {get: () => 'visible'});
            Object.defineProperty(document, 'hidden', {get: () => false});
        """)
        return p, browser, context, page

    @staticmethod
    async def open_login_modal_and_get_qr(
        page: Page, qr_capture: Dict[str, Optional[str]], qr_event: asyncio.Event
    ) -> str:
        """Mở trang chủ Douyin, kích hoạt popup đăng nhập và lấy mã QR."""
        await page.goto("https://www.douyin.com/", wait_until="commit", timeout=20000)

        btns = await page.locator("button").filter(has_text="登录").all()
        target_btn = btns[0] if btns else page.locator("button:has-text('登录')").first
        for b in btns:
            box = await b.bounding_box()
            if box and box["x"] > 900 and box["y"] < 80: target_btn = b; break

        await target_btn.click(timeout=5000)

        for _ in range(5):
            try:
                await asyncio.wait_for(qr_event.wait(), timeout=5.0)
                if qr_capture.get("src"): break
            except asyncio.TimeoutError:
                try:
                    tab = page.locator("li:has-text('扫码登录'), div:has-text('扫码登录')").first
                    if await tab.count() > 0 and await tab.is_visible(): await tab.click(timeout=1500)
                    else: await target_btn.click(timeout=2000, force=True)
                except Exception:
                    pass

        qr_src = qr_capture.get("src")
        if not qr_src:
            qr_img = page.locator("#douyin_login_comp_scan_code_qrcode img, img[src*='qrcode']")
            if await qr_img.count() > 0: qr_src = await qr_img.first.get_attribute("src")

        if not qr_src or not qr_src.startswith("data:image"):
            raise TimeoutError("Máy chủ Douyin phản hồi chậm gói tin QR, vui lòng bấm Thử lại.")
        return qr_src

    @staticmethod
    async def check_verify_needed(page: Page) -> Tuple[bool, Optional[str]]:
        """Kiểm tra màn hình nhận mã xác minh SMS '接收短信验证码' sau khi quét QR."""
        for scope in [page] + list(page.frames):
            try:
                if (await scope.locator("#uc-second-verify").count() > 0 or 
                    await scope.locator("text=接收短信验证码").count() > 0 or 
                    await scope.locator("text=短信已发送至").count() > 0):
                    mob = None
                    nodes = scope.locator("div:has-text('短信已发送至'), div:has-text('+84'), span:has-text('****')")
                    for idx in range(await nodes.count()):
                        txt = await nodes.nth(idx).inner_text()
                        m = re.search(r"(\+\d+[\*\d]+)", txt)
                        if m: mob = m.group(1).strip(); break
                        if "****" in txt: mob = txt.strip(); break
                    logger.info(f"Phát hiện màn hình SMS OTP Douyin! SĐT: {mob}")
                    return True, mob
            except Exception:
                pass
        return False, None

    @staticmethod
    async def check_is_scanned(page: Page) -> bool:
        """Kiểm tra xem người dùng đã quét mã trên điện thoại hay chưa (trước khi bấm xác nhận)."""
        for scope in [page] + list(page.frames):
            try:
                for t in ["已扫描", "请在手机上确认", "扫描成功"]:
                    if await scope.locator(f"text={t}").count() > 0: return True
            except Exception: pass
        return False

    @staticmethod
    async def submit_otp_code(page: Page, code: str) -> bool:
        """Tự động điền mã OTP vào đúng ô '请输入验证码' trong container #uc-second-verify và click '验证'."""
        target_scope: Union[Page, Frame] = page
        target_input: Optional[Locator] = None
        target_box: Optional[Any] = None

        # 1. Quét tìm ô input trên toàn bộ các frames (tránh bẫy bounding_box rỗng)
        selectors = [
            "#uc-second-verify input#button-input", "#uc-second-verify input[placeholder*='验证码']",
            "#uc-second-verify input[type='tel']", "#uc-second-verify input:not([type='hidden'])",
            "input#button-input", "input[placeholder*='验证码']:not([type='hidden'])",
            "input[type='tel']", "input[maxlength='6']",
        ]
        for scope in [page] + list(page.frames):
            for sel in selectors:
                loc = scope.locator(sel)
                if await loc.count() > 0:
                    for idx in range(await loc.count()):
                        inp = loc.nth(idx)
                        if await inp.get_attribute("type") == "hidden":
                            continue
                        target_scope, target_input = scope, inp
                        try:
                            target_box = await inp.bounding_box()
                        except Exception:
                            target_box = None
                        break
                if target_input:
                    break
            if target_input:
                break

        if not target_input:
            for scope in [page] + list(page.frames):
                loc = scope.locator("input:not([type='hidden'])")
                if await loc.count() > 0:
                    target_scope, target_input = scope, loc.first
                    break

        if target_input is None:
            raise RuntimeError("Không tìm thấy ô nhập mã xác minh '请输入验证码' trên Douyin.")

        logger.info(f"Tìm thấy ô OTP Douyin: tag={target_input}, box={target_box}")

        # 2. Điền mã bằng Hardware Mouse Click + Fill Force + Keyboard + DOM Setter
        if target_box:
            try:
                cx, cy = target_box["x"] + target_box["width"] / 2, target_box["y"] + target_box["height"] / 2
                await page.mouse.click(cx, cy)
                await asyncio.sleep(0.1)
            except Exception:
                pass

        try:
            await target_input.click(force=True, timeout=2000)
        except Exception:
            pass
        try:
            await target_input.fill(code, force=True, timeout=2000)
        except Exception:
            pass
        try:
            await target_input.press("Control+A")
            await target_input.press("Backspace")
            await target_input.press_sequentially(code, delay=60)
        except Exception:
            try:
                await page.keyboard.type(code, delay=60)
            except Exception:
                pass

        await target_scope.evaluate(
            """([sel, val]) => {
                const uc = document.querySelector('#uc-second-verify') || document;
                const inps = Array.from(uc.querySelectorAll('input:not([type="hidden"])'));
                const inp = inps.find(i => i.id === 'button-input' || (i.placeholder && i.placeholder.includes('验证码')) || i.maxLength === 6) || inps[0];
                if (inp) {
                    inp.focus();
                    const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                    if (s) { s.call(inp, val); } else { inp.value = val; }
                    inp.dispatchEvent(new Event('focus', { bubbles: true }));
                    inp.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: val }));
                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }""",
            ["#uc-second-verify input", code],
        )
        await asyncio.sleep(0.5)

        # Chụp ảnh Milestone 2: Đã nhập OTP vào ô input
        try:
            s2_path = os.path.join(get_scratch_dir(), "douyin_step2_typed_otp.png")
            await page.screenshot(path=s2_path)
            logger.info(f"[CHỤP ẢNH MILESTONE 2] -> {s2_path}")
        except Exception:
            pass

        # 3. Kích hoạt xác minh: Nhấn phím Enter + Click chính xác nút '验证'
        try:
            await target_input.press("Enter")
            await page.keyboard.press("Enter")
        except Exception:
            pass

        btn_loc = target_scope.locator("xpath=//button[normalize-space(.)='验证'] | //div[@role='button'][normalize-space(.)='验证'] | //*[contains(@class,'btn') or contains(@class,'button')][normalize-space(.)='验证']").last
        if await btn_loc.count() == 0:
            btn_loc = target_scope.locator("xpath=//*[normalize-space(text())='验证']").last

        if await btn_loc.count() > 0:
            try:
                b_box = await btn_loc.bounding_box()
                if b_box and b_box["width"] < 300 and b_box["height"] < 100:
                    await page.mouse.click(b_box["x"] + b_box["width"] / 2, b_box["y"] + b_box["height"] / 2)
                await btn_loc.click(force=True, timeout=1500)
                logger.info("Đã click nút '验证' thành công qua Mouse + Force!")
            except Exception:
                pass

        try:
            await target_scope.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('button, div, span')).reverse().find(el => {
                    const r = el.getBoundingClientRect();
                    return (el.innerText || '').trim() === '验证' && r.width > 25 && r.width < 300 && r.height > 15 && r.height < 100;
                });
                if (btn) { btn.click(); btn.dispatchEvent(new MouseEvent('click', { bubbles: true })); }
            }""")
        except Exception:
            pass

        await asyncio.sleep(0.8)

        # Chụp ảnh Milestone 3: Sau khi bấm nút xác minh
        try:
            s3_path = os.path.join(get_scratch_dir(), "douyin_step3_after_submit.png")
            await page.screenshot(path=s3_path)
            logger.info(f"[CHỤP ẢNH MILESTONE 3] -> {s3_path}")
        except Exception:
            pass

        # 4. Kiểm tra thông báo lỗi nếu mã sai
        try:
            for err_t in ["验证码错误", "验证码已过期", "验证码不正确", "验证失败"]:
                if await target_scope.locator(f"text={err_t}").count() > 0:
                    raise RuntimeError("Douyin phản hồi: Mã xác minh OTP không đúng hoặc đã hết hạn.")
        except RuntimeError:
            raise
        except Exception:
            pass
        return True

    @staticmethod
    async def resend_otp_code(page: Page) -> bool:
        """Nhấn nút gửi lại mã xác minh SMS trên Douyin."""
        scopes = [page] + list(page.frames)
        for scope in scopes:
            resend_btns = [
                scope.locator("text=重新发送"),
                scope.locator("text=获取验证码"),
                scope.locator("*:has-text('重新发送')"),
            ]
            for btn_loc in resend_btns:
                if await btn_loc.count() > 0:
                    btn = btn_loc.last
                    if await btn.is_visible():
                        await btn.click(timeout=5000, force=True)
                        logger.info("Đã bấm gửi lại mã xác minh trên Douyin!")
                        return True
        raise RuntimeError("Nút gửi lại mã xác minh đang trong thời gian đếm ngược hoặc không sẵn sàng.")

    @staticmethod
    async def cleanup_session(p, browser, context):
        """Đóng an toàn các tiến trình Playwright."""
        for res in [context, browser, p]:
            if res:
                try:
                    action = res.close() if hasattr(res, "close") else res.stop()
                    if asyncio.iscoroutine(action):
                        await action
                except Exception:
                    pass
