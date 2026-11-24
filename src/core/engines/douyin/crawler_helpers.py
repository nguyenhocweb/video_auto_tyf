import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("douyin_crawler_helpers")

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TZ_VN = timezone(timedelta(hours=7))

# Script JavaScript khống chế chính xác danh sách bài đăng tác giả
# Quét sâu qua SSR State, RENDER_DATA, và bộ lọc DOM đa selector (hỗ trợ video, note, modal_id)
# KHÓA CHẶT TƯỜNG LỬA: Tuyệt đối cấm cào bừa bãi vào trending, recommend, recent_viewed, document.body
DOM_EXTRACT_AUTHOR_POSTS_JS = """(targetSecUid) => {
    const results = [];
    const seenIds = new Set();

    function pushItem(id, item, href, fallbackCover, fallbackCaption, fallbackLikes) {
        if (!id || seenIds.has(String(id))) return;
        // KHÓA TÁC GIẢ CHẶT CHẼ: Nếu có targetSecUid và item có author sec_uid -> Bắt buộc phải trùng khớp!
        if (targetSecUid) {
            const authorSec = item?.author?.sec_uid || item?.author_sec_uid;
            if (authorSec && authorSec !== targetSecUid) return;
        }
        seenIds.add(String(id));
        const cover = item?.video?.cover?.url_list?.[0] || item?.images?.[0]?.url_list?.[0] || fallbackCover || '';
        const caption = item?.desc || fallbackCaption || `Video ${id}`;
        const createTime = item?.create_time || 0;
        const likes = item?.statistics?.digg_count !== undefined ? String(item.statistics.digg_count) : (fallbackLikes || '');
        results.push({
            link: `https://www.douyin.com/video/${id}`,
            cover: cover,
            caption: caption.trim(),
            timeText: '',
            createTime: createTime,
            likesText: likes
        });
    }

    // 1. Quét CHÍNH XÁC cấu trúc user-detail của đúng tác giả trong SSR State
    // TUYỆT ĐỐI CẤM duyệt vào cards, data, recommend, history, sidebar!
    function extractFromSSR(root) {
        if (!root || typeof root !== 'object') return;
        const scope = root.__DEFAULT_SCOPE__ || root;
        for (const [k, v] of Object.entries(scope)) {
            if (k.includes('user-detail') || k.includes('user-post')) {
                const list = v?.post?.data || v?.postList || v?.aweme_list || [];
                if (Array.isArray(list)) {
                    list.forEach(item => {
                        const id = item?.aweme_id || item?.item_id;
                        const itSec = item?.author?.sec_uid;
                        if (id && (!targetSecUid || !itSec || itSec === targetSecUid)) {
                            pushItem(id, item);
                        }
                    });
                }
            }
        }
    }

    try {
        const u = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
        if (u && u.textContent) extractFromSSR(JSON.parse(u.textContent));
    } catch(e) {}

    try {
        const r = document.getElementById('RENDER_DATA');
        if (r && r.textContent) extractFromSSR(JSON.parse(decodeURIComponent(r.textContent)));
    } catch(e) {}

    if (results.length > 0) return results;

    // 2. KHÓA VÙNG CHẶT CHẼ TRÊN DOM:
    // CHỈ TÌM TRONG ĐÚNG CONTAINER BÀI ĐĂNG CỦA TÁC GIẢ ([data-e2e="user-post-list"], [data-e2e="scroll-list"])
    // TUYỆT ĐỐI CẤM fallback ra document.body hoặc main để chống cào nhầm video gợi ý/trending/lịch sử xem!
    const postContainer = document.querySelector(
        '[data-e2e="user-post-list"], [data-e2e="scroll-list"], [data-e2e="user-tab-content"], ' +
        'ul[class*="post-list"], div[class*="post-list"], div[class*="user-post"]'
    );
    if (!postContainer) {
        // Nếu không có container bài đăng của tác giả -> Hủy ngay, trả về rỗng, KHÔNG ĐƯỢC CÀO TOÀN TRANG!
        return results;
    }

    const cards = postContainer.querySelectorAll('a[href*="/video/"], a[href*="/note/"], a[href*="modal_id="]');
    cards.forEach(a => {
        // Loại bỏ links trong header, navbar, sidebar gợi ý
        if (a.closest('header, nav, aside, [class*="header"], [class*="nav-"]')) return;

        // Bỏ qua video ghim (置顶 - Pinned) từ các năm trước
        const pinBadge = a.querySelector('[class*="pin"], [class*="top"], [data-e2e*="pin"]');
        if (pinBadge && (pinBadge.innerText || '').includes('置顶')) return;

        const href = a.href || a.getAttribute('href') || '';
        // Bỏ qua các link khuyến nghị SEO của Douyin (Baiduspider)
        if (href.includes('source=Baiduspider')) return;

        // Bỏ qua thẻ placeholder che màn hình đăng nhập (không có nội dung video)
        const rawText = (a.innerText || '') + (a.getAttribute('title') || '');
        if (rawText.includes('看更多') && rawText.includes('登录')) return;

        const match = href.match(/\\/(?:video|note)\\/(\\d+)/) || href.match(/modal_id=(\\d+)/);
        if (!match) return;
        const vidId = match[1];

        const img = a.querySelector('img') || a.closest('li, div')?.querySelector('img');
        let cover = img ? (img.src || img.getAttribute('data-src') || '') : '';
        if (!cover) {
            const bg = a.querySelector('[style*="background-image"]') || a;
            const mBg = (bg.getAttribute('style') || '').match(/url\\(["']?(.*?)["']?\\)/);
            if (mBg) cover = mBg[1];
        }

        const desc = a.querySelector('p, span, [class*="title"], [class*="desc"]') || a;
        const caption = (desc ? desc.innerText.trim() : '') || a.getAttribute('title') || '';
        const likeEl = a.querySelector('[class*="like"], [class*="count"], [data-e2e*="like"]');

        pushItem(vidId, null, href, cover, caption, likeEl ? likeEl.innerText.trim() : '');
    });
    return results;
}"""


class CrawlerHelpers:
    @staticmethod
    def format_aweme_list(
        aweme_list: List[Dict[str, Any]], limit: int, now_vn: datetime, target_sec_uid: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Chuẩn hóa danh sách video từ API, kiểm tra nghiêm ngặt author sec_uid để loại bỏ video ngoài."""
        video_items = []
        for item in aweme_list:
            # KIỂM TRA AUTHOR SEC_UID: Chỉ nhận đúng video của tác giả kênh này!
            author = item.get("author", {})
            item_sec = author.get("sec_uid")
            if target_sec_uid and item_sec and item_sec != target_sec_uid:
                logger.warning(f"Bỏ qua video {item.get('aweme_id')} vì author sec_uid không khớp kênh!")
                continue

            item_id = str(item.get("aweme_id", ""))
            create_ts = int(item.get("create_time", 0))
            dt = datetime.fromtimestamp(create_ts, tz=TZ_VN) if create_ts else now_vn
            v_obj = item.get("video", {})
            m_urls = item.get("music", {}).get("play_url", {}).get("url_list", [])
            music_url = m_urls[0] if (m_urls and isinstance(m_urls[0], str)) else None
            play_urls = v_obj.get("play_addr", {}).get("url_list", []) or v_obj.get("play_addr_h264", {}).get("url_list", [])
            clean_stream = play_urls[0] if (play_urls and isinstance(play_urls[0], str)) else None
            covers = v_obj.get("cover", {}).get("url_list", [])
            cover_url = covers[0] if covers else None
            video_items.append({
                "item_id": item_id,
                "title": (item.get("desc") or "").strip(),
                "video_url": f"https://www.douyin.com/video/{item_id}",
                "cover_url": cover_url,
                "clean_stream_url": clean_stream,
                "music_url": music_url,
                "duration": round(float(v_obj.get("duration", 0)) / 1000.0, 2),
                "is_today": (dt.date() == now_vn.date()),
                "crawled_date": dt.strftime("%Y-%m-%d"),
                "publish_time": dt.strftime("%d/%m/%Y %H:%M"),
                "created_timestamp": create_ts,
                "likes_count": item.get("statistics", {}).get("digg_count", 0),
                "author_sec_uid": item_sec,
                "author_nickname": author.get("nickname"),
            })
            if len(video_items) >= limit:
                break
        return video_items

    @staticmethod
    def format_dom_cards(
        cards: List[Dict[str, Any]], limit: int, now_vn: datetime, sec_uid: Optional[str], creator_name: str
    ) -> List[Dict[str, Any]]:
        """Chuẩn hóa danh sách thẻ bài đăng cào từ DOM."""
        video_items = []
        for card in cards[:limit]:
            m = re.search(r"/(?:video|note)/(\d+)", card.get("link", "")) or re.search(r"modal_id=(\d+)", card.get("link", ""))
            item_id = m.group(1) if m else ""
            if not item_id:
                continue
            ts = int(card.get("createTime") or 0)
            if ts > 0:
                dt = datetime.fromtimestamp(ts, tz=TZ_VN)
                is_today, c_date, p_time = (dt.date() == now_vn.date()), dt.strftime("%Y-%m-%d"), dt.strftime("%d/%m/%Y %H:%M")
            else:
                hint = (card.get("timeText") or "").strip()
                is_today = bool(hint and any(x in hint.lower() for x in ["hôm nay", "today", "giờ trước"]))
                c_date, p_time = now_vn.strftime("%Y-%m-%d"), hint or now_vn.strftime("%d/%m/%Y %H:%M")
            video_items.append({
                "item_id": item_id, "title": (card.get("caption") or "").strip(),
                "video_url": f"https://www.douyin.com/video/{item_id}", "cover_url": card.get("cover"),
                "is_today": is_today, "crawled_date": c_date, "publish_time": p_time,
                "created_timestamp": ts or int(now_vn.timestamp()), "likes_count": 0,
                "author_sec_uid": sec_uid, "author_nickname": creator_name,
            })
        return video_items

    @classmethod
    async def crawl_via_api(cls, sec_uid: str, limit: int) -> Optional[Dict[str, Any]]:
        """Thử lấy danh sách video qua API mobile chính thức của Douyin."""
        if not sec_uid:
            return None
        api_url = f"https://www.iesdouyin.com/web/api/v2/user/post/?sec_uid={sec_uid}&count={limit}&max_cursor=0"
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": MOBILE_UA, "Referer": f"https://www.douyin.com/user/{sec_uid}"},
                timeout=8.0
            ) as client:
                res = await client.get(api_url)
                if res.status_code == 200:
                    aweme_list = res.json().get("aweme_list", [])
                    if aweme_list:
                        now_vn = datetime.now(TZ_VN)
                        author = aweme_list[0].get("author", {})
                        video_items = cls.format_aweme_list(aweme_list, limit, now_vn, target_sec_uid=sec_uid)
                        if video_items:
                            return {
                                "creator_name": author.get("nickname", "Douyin Creator"),
                                "creator_avatar": author.get("avatar_thumb", {}).get("url_list", [None])[0],
                                "channel_url": f"https://www.douyin.com/user/{sec_uid}",
                                "total_works": len(aweme_list),
                                "today_count": len(video_items),
                                "videos": video_items,
                            }
        except Exception as exc:
            logger.debug(f"API crawl fallback error: {exc}")
        return None

    @staticmethod
    def get_active_douyin_cookie() -> str:
        """Đọc Cookie Douyin ưu tiên từ cache, sau đó đến MongoDB, rồi đến .env."""
        try:
            from src.modules.creator.douyin.service import DouyinSessionService
            cached = DouyinSessionService.get_cached_cookie()
            if cached:
                return cached
        except Exception:
            pass
        try:
            from src.modules.creator.douyin.repository import DouyinMongoRepository
            sess = DouyinMongoRepository()._get_active_session_sync()
            if sess and sess.get("cookies_str"):
                return sess["cookies_str"]
        except Exception:
            pass
        try:
            from src.core.config import settings
            if getattr(settings, "DOUYIN_COOKIE", None):
                return settings.DOUYIN_COOKIE
        except Exception:
            pass
        try:
            from pathlib import Path
            for p in [Path("be/.env"), Path(".env"), Path(__file__).resolve().parents[4] / ".env"]:
                if p.exists():
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("DOUYIN_COOKIE="):
                                val = line.strip().split("=", 1)[1].strip()
                                if val.startswith('"') and val.endswith('"'):
                                    val = val[1:-1]
                                return val
        except Exception:
            pass
        return ""
