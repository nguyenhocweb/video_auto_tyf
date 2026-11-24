import os
import re
import sys
import asyncio
import logging
from typing import Dict, Any, Optional, Tuple, List
import httpx
from playwright.async_api import async_playwright
from src.core.config import settings
from src.core.engines.douyin.crawler_helpers import CrawlerHelpers

logger = logging.getLogger("douyin_extractor")

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class DouyinExtractor:
    @staticmethod
    def extract_url(raw_text: str) -> str:
        """Trích xuất URL douyin từ chuỗi văn bản người dùng nhập."""
        pattern = r"(https?://[a-zA-Z0-9.-]*douyin\.com/[^\s,，。]+)"
        match = re.search(pattern, raw_text)
        if not match:
            raise ValueError("Không tìm thấy đường link Douyin hợp lệ trong nội dung.")
        return match.group(1).strip()

    @staticmethod
    def extract_title_hint(raw_text: str) -> Optional[str]:
        """Trích xuất tiêu đề video đi kèm trong chuỗi chia sẻ nếu có."""
        m = re.search(r"[:/／]\s*([^:/／\n\r]+?)\s*https?://", raw_text)
        return m.group(1).strip() if (m and len(m.group(1).strip()) > 2 and not m.group(1).strip().startswith("http")) else None

    @staticmethod
    def _generate_shortcode_candidates(code: str) -> List[str]:
        """Tự động sinh các biến thể ký tự dễ nhầm lẫn (I vs l, 0 vs O, 1 vs l) để sửa lỗi gõ/copy."""
        pairs = [("I", "l"), ("l", "I"), ("0", "O"), ("O", "0"), ("1", "l"), ("l", "1")]
        candidates = [code] + [code.replace(a, b) for a, b in pairs if a in code]
        return list(dict.fromkeys(candidates))

    @classmethod
    async def resolve_canonical_url(cls, url: str) -> Tuple[str, str]:
        """Follow redirect nếu là link rút gọn và lấy ID video, có cơ chế tự sửa sai ký tự."""
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15",
            "Referer": "https://www.douyin.com/",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=12.0) as client:
            res = await client.get(url)
            final_url = str(res.url)

            id_m = re.search(r"/video/(\d+)", final_url) or re.search(r"(\d{18,21})", final_url) or re.search(r"modal_id=(\d+)", final_url)
            if id_m:
                return id_m.group(1), final_url

            code_match = re.search(r"v\.douyin\.com/([a-zA-Z0-9_-]+)", url)
            if code_match:
                original_code = code_match.group(1)
                candidates = cls._generate_shortcode_candidates(original_code)
                for cand in candidates[1:]:
                    cand_url = f"https://v.douyin.com/{cand}/"
                    try:
                        c_res = await client.get(cand_url)
                        c_final = str(c_res.url)
                        c_match = re.search(r"/video/(\d+)", c_final) or re.search(r"(\d{18,21})", c_final)
                        if c_match:
                            logger.info(f"Đã tự động sửa sai ký tự link rút gọn: {original_code} -> {cand}")
                            return c_match.group(1), c_final
                    except Exception:
                        pass

            raise ValueError("Không thể tìm thấy mã ID video từ đường link Douyin này.")

    @classmethod
    async def _extract_with_playwright(cls, item_id: str, title_hint: Optional[str]) -> Dict[str, Any]:
        """Bóc tách luồng video và thông tin chi tiết bằng Playwright Async."""
        video_target_url = f"https://www.douyin.com/video/{item_id}"
        captured_stream_url: Optional[str] = None
        music_stream_url: Optional[str] = None
        page_title = title_hint or "Video Douyin"
        author_name = "Douyin Creator"
        author_avatar: Optional[str] = None
        author_uid: Optional[str] = None
        author_sec_uid: Optional[str] = None
        cover_url: Optional[str] = None
        duration = 0.0

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
                except Exception as launch_err:
                    logger.warning(f"Lỗi khởi động channel Chrome/Edge: {launch_err}. Thử launch mặc định...")
                    browser = await p.chromium.launch(
                        headless=settings.PLAYWRIGHT_HEADLESS,
                        args=["--no-sandbox", "--disable-setuid-sandbox"],
                    )
                context = await browser.new_context(
                    user_agent=DESKTOP_UA,
                    viewport={"width": 1280, "height": 720},
                    locale="zh-CN",
                )
                try:
                    c_str = CrawlerHelpers.get_active_douyin_cookie()
                    if c_str:
                        v_keys = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt", "passport_csrf_token", "ttwid", "odin_tt"}
                        c_list = [{"name": k.strip(), "value": v.strip(), "domain": ".douyin.com", "path": "/"} for it in c_str.split(";") if "=" in it for k, v in [it.strip().split("=", 1)] if k.strip() in v_keys]
                        await context.add_cookies(c_list)
                except Exception:
                    pass
                page = await context.new_page()
                event = asyncio.Event()

                async def handle_response(response):
                    nonlocal captured_stream_url, music_stream_url
                    nonlocal page_title, author_name, author_avatar, author_uid, author_sec_uid, cover_url, duration

                    u = response.url
                    # 1. Chặn bắt dữ liệu chi tiết chính thức từ API aweme/detail của Douyin
                    if "aweme/v1/web/aweme/detail" in u and response.status == 200:
                        try:
                            payload = await response.json()
                            aweme = payload.get("aweme_detail", {})
                            if aweme:
                                if aweme.get("desc"):
                                    page_title = aweme["desc"].strip()
                                author = aweme.get("author", {})
                                if author.get("nickname"):
                                    author_name = author["nickname"].strip()
                                author_uid = str(author.get("uid") or "")
                                author_sec_uid = str(author.get("sec_uid") or "")
                                if author.get("avatar_thumb", {}).get("url_list"):
                                    author_avatar = author["avatar_thumb"]["url_list"][0]

                                vid_info = aweme.get("video", {})
                                if vid_info.get("duration"):
                                    duration = round(float(vid_info["duration"]) / 1000.0, 2)
                                if vid_info.get("cover", {}).get("url_list"):
                                    cover_url = vid_info["cover"]["url_list"][0]

                                # Lấy luồng video sạch 1080p muxed (có cả tiếng & hình)
                                play_urls = vid_info.get("play_addr", {}).get("url_list", [])
                                if play_urls and isinstance(play_urls[0], str):
                                    first_stream_url = play_urls[0]
                                    captured_stream_url = first_stream_url
                                    logger.info(f"Đã bắt được 1080p URL từ aweme/detail: {first_stream_url[:80]}")

                                music = aweme.get("music", {})
                                m_list = music.get("play_url", {}).get("url_list", [])
                                if m_list and isinstance(m_list[0], str) and m_list[0].startswith("http"):
                                    music_stream_url = m_list[0]
                                elif music.get("play_url", {}).get("uri") and str(music["play_url"]["uri"]).startswith("http"):
                                    music_stream_url = music["play_url"]["uri"]

                                if captured_stream_url:
                                    event.set()
                        except Exception as e:
                            logger.debug(f"Lỗi phân tích aweme/detail: {e}")

                    # 2. Luồng dự phòng: bắt trực tiếp gói phản hồi MP4/Video stream
                    ct = response.headers.get("content-type", "")
                    if ("video/mp4" in ct or "video" in ct) and "uuu_265" not in u:
                        if ("douyinvod.com" in u or "zjcdn.com" in u or "video/tos" in u):
                            if "media-audio" in u or "audio" in u:
                                if not music_stream_url:
                                    music_stream_url = u
                            elif "media-video" not in u:
                                captured_stream_url = u
                                event.set()
                            elif not captured_stream_url:
                                captured_stream_url = u

                page.on("response", lambda r: asyncio.create_task(handle_response(r)))

                # Điều hướng trực tiếp đến URL video của Douyin (dùng commit để không bị treo bởi script theo dõi mạng)
                try:
                    await page.goto(video_target_url, wait_until="commit", timeout=25000)
                except Exception as nav_err:
                    logger.warning(f"page.goto cảnh báo điều hướng ({nav_err}). Vẫn tiếp tục bắt luồng video...")
                await page.wait_for_timeout(1500)

                # Gỡ bỏ modal đăng nhập và kích hoạt phát video tự động nếu cần
                try:
                    await page.evaluate("""() => {
                        document.querySelectorAll("div[role='dialog'], [class*='login'], [class*='modal']").forEach(e => e.remove());
                        const v = document.querySelector('video');
                        if (v) {
                            v.muted = true;
                            v.play().catch(e => console.log('play err', e));
                        }
                    }""")
                except Exception as e:
                    logger.debug(f"Lỗi kích hoạt video qua DOM: {e}")

                # Đợi dữ liệu bóc tách từ API hoặc network stream (tối thiểu 35s cho video dài/mạng quốc tế)
                wait_sec = max(35.0, getattr(settings, "DOUYIN_TIMEOUT_SEC", 35.0))
                try:
                    await asyncio.wait_for(event.wait(), timeout=wait_sec)
                except asyncio.TimeoutError:
                    pass

                # Luôn bổ sung thông tin tác giả, cover và thời lượng từ DOM nếu thiếu
                if not author_sec_uid or not cover_url or duration == 0:
                    try:
                        dom_info = await page.evaluate("""() => {
                            const v = document.querySelector('video');
                            let aEl = document.querySelector("a[href*='/user/MS4wLjAB']");
                            if (!aEl) {
                                aEl = Array.from(document.querySelectorAll("a[href*='/user/']")).find(el => {
                                    const h = el.getAttribute('href') || el.href || '';
                                    return !h.includes('/user/self') && !el.closest('header, nav, aside, [class*="sidebar"]');
                                });
                            }
                            const href = aEl ? (aEl.getAttribute('href') || aEl.href || '') : '';
                            const mSec = href.match(/user\\/(MS4wLjAB[a-zA-Z0-9_-]+)/);
                            const rawNick = aEl ? (aEl.innerText || '') : '';
                            const cleanNick = rawNick.replace(/[@\\s]|认证徽章|徽章/g, '');
                            const validNick = (cleanNick && !['我的', 'self', '首页'].includes(cleanNick)) ? cleanNick : null;
                            const coverImg = document.querySelector("video[poster], img[src*='douyinpic'], img[src*='byteimg']");
                            return {
                                duration: v ? v.duration : 0,
                                author: validNick,
                                sec_uid: mSec ? mSec[1] : null,
                                cover: v && v.poster ? v.poster : (coverImg ? coverImg.src : null)
                            };
                        }""")
                        if dom_info:
                            if duration == 0 and dom_info.get("duration") and str(dom_info["duration"]) != "nan":
                                duration = round(float(dom_info["duration"]), 2)
                            if (author_name == "Douyin Creator" or not author_sec_uid) and dom_info.get("author"):
                                author_name = dom_info["author"].strip()
                            if not author_sec_uid and dom_info.get("sec_uid"):
                                author_sec_uid = dom_info["sec_uid"].strip()
                            if not cover_url and dom_info.get("cover"):
                                cover_url = dom_info["cover"]
                    except Exception as e:
                        logger.debug(f"Lỗi đọc DOM video: {e}")

                await browser.close()

        except Exception as e:
            logger.error(f"Lỗi Playwright bóc tách video: {e}")

        if not captured_stream_url:
            raise ValueError(
                "Không thể trích xuất luồng video sạch không logo. "
                "Có thể video này ở chế độ riêng tư hoặc Douyin tạm thời giới hạn IP."
            )

        return {
            "item_id": item_id,
            "title": page_title,
            "duration": duration,
            "video_url": captured_stream_url,
            "cover_url": cover_url,
            "music_url": music_stream_url,
            "author": {
                "nickname": author_name,
                "avatar": author_avatar,
                "uid": author_uid,
                "sec_uid": author_sec_uid,
            },
            "source_platform": "douyin",
        }

    @classmethod
    async def extract_no_watermark_video(cls, raw_input: str) -> Dict[str, Any]:
        """Entrypoint bóc tách video Douyin, tự động xử lý event loop Proactor trên Windows."""
        clean_url = cls.extract_url(raw_input)
        title_hint = cls.extract_title_hint(raw_input)
        item_id, canonical_url = await cls.resolve_canonical_url(clean_url)
        logger.info(f"Bắt đầu bóc tách video ID {item_id} từ URL {canonical_url}")

        if sys.platform == "win32":
            def _runner():
                loop = asyncio.ProactorEventLoop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(cls._extract_with_playwright(item_id, title_hint))
                finally:
                    loop.close()

            return await asyncio.to_thread(_runner)
        else:
            return await cls._extract_with_playwright(item_id, title_hint)
