import os
import sys
import re
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from playwright.async_api import async_playwright
from src.core.config import settings
from src.core.engines.douyin.url_resolver import DouyinUrlResolver
from src.core.engines.douyin.crawler_helpers import CrawlerHelpers, DOM_EXTRACT_AUTHOR_POSTS_JS, TZ_VN

logger = logging.getLogger("douyin_channel_crawler")


class DouyinChannelCrawler:
    """Crawler bóc tách video kênh Douyin chính xác 100%, bảo vệ toàn vẹn nguồn kênh chống lọt video ngoài."""

    @staticmethod
    def extract_url(raw_text: str) -> str:
        return DouyinUrlResolver.extract_url(raw_text)

    @classmethod
    async def resolve_channel_url(cls, raw_input: str) -> Tuple[str, Optional[str]]:
        return await DouyinUrlResolver.resolve_channel_url(raw_input)

    @staticmethod
    def _format_aweme_list(aweme_list: List[Dict], limit: int, now_vn: datetime) -> List[Dict[str, Any]]:
        return CrawlerHelpers.format_aweme_list(aweme_list, limit, now_vn)

    @staticmethod
    async def _safe_eval(page, script: str, *args, retries: int = 2) -> Any:
        """Thực thi JS an toàn, chống vỡ context (Execution context destroyed) khi trang reload/navigate."""
        for attempt in range(retries):
            try:
                if page.is_closed():
                    return None
                return await page.evaluate(script, *args)
            except Exception as e:
                err_msg = str(e).lower()
                if "destroyed" in err_msg or "navigation" in err_msg:
                    logger.debug(f"Context bị destroy lần {attempt + 1}, đợi 0.8s...")
                    await asyncio.sleep(0.8)
                    continue
                return None
        return None

    @classmethod
    async def _click_red_refresh_text(cls, page) -> bool:
        """Tìm chính xác thẻ chữ màu đỏ '刷新' trong '服务异常，重新刷新拉取数据' và click."""
        js = """() => {
            for (const el of document.querySelectorAll('*')) {
                if (el.children.length > 0) continue;
                const txt = (el.innerText || el.textContent || '').trim();
                if (txt === '刷新' || txt === '重新刷新') {
                    const ctx = (el.closest('div, p, section')?.innerText || '') + (el.parentElement?.innerText || '');
                    if (ctx.includes('服务异常') || ctx.includes('拉取数据') || ctx.includes('重新')) {
                        el.scrollIntoView({ behavior: 'instant', block: 'center' });
                        const r = el.getBoundingClientRect();
                        ['mousedown', 'mouseup', 'click'].forEach(evt => {
                            el.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 }));
                        });
                        el.click();
                        return { found: true, x: r.left + r.width / 2, y: r.top + r.height / 2 };
                    }
                }
            }
            return { found: false };
        }"""
        res = await cls._safe_eval(page, js)
        if res and res.get("found"):
            x, y = res.get("x", 0), res.get("y", 0)
            if x > 0 and y > 0:
                try:
                    await page.mouse.click(x, y)
                except Exception:
                    pass
            return True
        return False

    @classmethod
    async def crawl_today_videos(
        cls, channel_input: str, limit: int = 20
    ) -> Dict[str, Any]:
        """Cào danh sách video mới nhất từ đúng kênh tác giả, chống cào nhầm video gợi ý/trang chủ."""
        channel_url, sec_uid = await cls.resolve_channel_url(channel_input)
        logger.info(f"Bắt đầu quét kênh: {channel_url} (sec_uid: {sec_uid})")

        # 1. Thử lấy qua API trước (nhanh và chuẩn 100% video của đúng tác giả)
        if sec_uid:
            api_res = await CrawlerHelpers.crawl_via_api(sec_uid, limit)
            if api_res and len(api_res.get("videos", [])) > 0:
                logger.info(f"Đã quét được {len(api_res['videos'])} video chính chủ qua API trực tiếp!")
                return api_res

        # 2. Quét qua Playwright với network response capture và kiểm soát URL nghiêm ngặt
        creator_name = "Douyin Creator"
        creator_avatar: Optional[str] = None
        total_works = 0
        captured_videos: List[Dict[str, Any]] = []
        dom_cards: List[Dict[str, Any]] = []
        is_login_wall = False

        try:
            async with async_playwright() as p:
                launch_kwargs: Dict[str, Any] = {
                    "headless": settings.PLAYWRIGHT_HEADLESS,
                    "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"],
                }
                if sys.platform == "win32":
                    chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
                    edge_path = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
                    if os.path.exists(chrome_path):
                        launch_kwargs["channel"] = "chrome"
                    elif os.path.exists(edge_path):
                        launch_kwargs["channel"] = "msedge"
                try:
                    browser = await p.chromium.launch(**launch_kwargs)
                except Exception as l_err:
                    logger.warning(f"Lỗi khởi động channel Chrome/Edge: {l_err}. Thử launch mặc định...")
                    launch_kwargs.pop("channel", None)
                    browser = await p.chromium.launch(**launch_kwargs)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 900}, locale="zh-CN"
                )
                page = await context.new_page()
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(document, 'visibilityState', {get: () => 'visible'});
                    Object.defineProperty(document, 'hidden', {get: () => false});
                """)

                # 1. Bơm Cookie phiên người dùng (ưu tiên cache/DB/env để vào đúng phiên tài khoản)
                try:
                    c_str = CrawlerHelpers.get_active_douyin_cookie()
                    if c_str:
                        v_keys = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt", "passport_csrf_token", "ttwid", "odin_tt"}
                        c_list = [{"name": k.strip(), "value": v.strip(), "domain": ".douyin.com", "path": "/"} for it in c_str.split(";") if "=" in it for k, v in [it.strip().split("=", 1)] if k.strip() in v_keys]
                        await context.add_cookies(c_list)
                except Exception:
                    pass

                event = asyncio.Event()

                # Bắt gói API network khi nạp danh sách video của tác giả
                async def handle_response(response):
                    u = response.url
                    if "aweme/post" in u or "web/aweme/post" in u:
                        logger.info(f"HANDLE RESP: [{response.status}] {u[:80]}")
                        if response.status == 200:
                            try:
                                data = await response.json()
                                items = data.get("aweme_list", [])
                                logger.info(f"aweme_list count: {len(items)}")
                                if items:
                                    author_items = []
                                    for it in items:
                                        it_sec = it.get("author", {}).get("sec_uid")
                                        if sec_uid:
                                            if it_sec and it_sec == sec_uid:
                                                author_items.append(it)
                                        else:
                                            author_items.append(it)
                                    logger.info(f"author_items count: {len(author_items)}")
                                    if author_items:
                                        captured_videos.extend(author_items)
                                        event.set()
                            except Exception as ex:
                                if "Target page, context or browser has been closed" in str(ex):
                                    logger.debug("Trang/trình duyệt đã đóng khi nhận phản hồi.")
                                else:
                                    logger.error(f"Error parsing json in handle_response: {ex}")
                page.on("response", handle_response)

                try:
                    await page.goto(channel_url, wait_until="commit", timeout=25000)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=4000)
                    except Exception:
                        pass

                    # KIỂM SOÁT URL CHẶT CHẼ: Nếu Douyin chuyển hướng sang trang chủ (không còn /user/) -> HỦY NGAY!
                    current_url = page.url
                    if "/user/" not in current_url:
                        logger.warning(
                            f"Douyin đã chuyển hướng ({current_url}) ra khỏi trang tác giả {channel_url}. "
                            "HỦY CÀO để tránh cào nhầm video gợi ý/trang chủ!"
                        )
                        await browser.close()
                        return {
                            "creator_name": creator_name,
                            "creator_avatar": creator_avatar,
                            "channel_url": channel_url,
                            "total_works": 0,
                            "today_count": 0,
                            "videos": [],
                        }

                    # Mở khóa scroll trang nếu có overlay
                    await cls._safe_eval(page, """() => {
                        document.querySelectorAll('[class*="login-mask"], [class*="login-dialog"]').forEach(el => el.remove());
                        document.body.style.overflow = 'auto';
                        document.documentElement.style.overflow = 'auto';
                    }""")

                    await page.wait_for_timeout(1000)

                    # Bắt và click chính xác chữ màu đỏ "刷新" trong thông báo "服务异常，重新刷新拉取数据"
                    for _ in range(3):
                        if captured_videos:
                            break
                        if await cls._click_red_refresh_text(page):
                            logger.info("Đã phát hiện và click chữ màu đỏ '刷新' để kích hoạt tải video...")
                            try:
                                await asyncio.wait_for(event.wait(), timeout=3.0)
                            except asyncio.TimeoutError:
                                pass
                            if captured_videos:
                                break
                        await asyncio.sleep(0.5)

                    # Cuộn trang nhiều nhịp để kích hoạt nạp danh sách video
                    for _ in range(5):
                        if captured_videos:
                            break
                        await cls._click_red_refresh_text(page)
                        await cls._safe_eval(page, "() => window.scrollBy(0, 800)")
                        try:
                            await asyncio.wait_for(event.wait(), timeout=2.0)
                        except asyncio.TimeoutError:
                            pass

                    # Luôn cập nhật tên, avatar và tổng tác phẩm từ DOM để khớp thực tế kênh
                    if not page.is_closed():
                        info = await cls._safe_eval(page, """() => {
                            const n = document.querySelector("h1[class*='name'], [data-e2e='user-info'] h1, .account-name, [class*='nickname']")?.innerText?.trim();
                            const a = document.querySelector("img[class*='avatar'], .avatar img, [data-e2e='user-info'] img")?.src;
                            const w = document.querySelector("[data-e2e='user-tab-count'], [class*='tab-count']")?.innerText || '';
                            const m = w.match(/\\d+/);
                            return { name: n, avatar: a, works: m ? parseInt(m[0], 10) : 0 };
                        }""")
                        if info:
                            creator_name = info.get("name") or creator_name
                            creator_avatar = info.get("avatar") or creator_avatar
                            total_works = info.get("works") or total_works
                except Exception as e:
                    logger.warning(f"Lỗi khi load trang Douyin Playwright: {e}")

                # Fallback DOM an toàn: CHỈ tìm trong container [data-e2e="user-post-list"] của đúng tác giả
                if not captured_videos and not page.is_closed():
                    cards = await cls._safe_eval(page, DOM_EXTRACT_AUTHOR_POSTS_JS, sec_uid)
                    if isinstance(cards, list):
                        dom_cards = cards
                    login_text = await cls._safe_eval(page, "() => (document.body ? document.body.innerText : '')")
                    if login_text and "看更多" in login_text and "登录" in login_text:
                        is_login_wall = True

                await browser.close()
        except Exception as play_err:
            logger.warning(f"Lỗi Playwright khi quét kênh {channel_url}: {play_err}")

        # Tổng hợp danh sách kết quả
        now_vn = datetime.now(TZ_VN)
        video_items = []

        if captured_videos:
            first_author = captured_videos[0].get("author", {})
            if first_author.get("nickname"):
                creator_name = first_author["nickname"].strip()
            if first_author.get("avatar_thumb", {}).get("url_list"):
                creator_avatar = first_author["avatar_thumb"]["url_list"][0]
            video_items = CrawlerHelpers.format_aweme_list(captured_videos, limit, now_vn, target_sec_uid=sec_uid)
        else:
            video_items = CrawlerHelpers.format_dom_cards(dom_cards, limit, now_vn, sec_uid, creator_name)

        return {
            "creator_name": creator_name,
            "creator_avatar": creator_avatar,
            "channel_url": channel_url,
            "total_works": total_works or len(video_items),
            "today_count": len(video_items),
            "videos": video_items,
            "login_required": is_login_wall,
        }
