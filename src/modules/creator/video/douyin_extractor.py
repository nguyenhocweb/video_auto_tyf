import re
import logging
from typing import Optional, Tuple
import httpx
from src.modules.creator.video.schemas import VideoMetadataResponse, VideoAuthorInfo

logger = logging.getLogger("douyin_extractor")

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class DouyinExtractor:
    @staticmethod
    def extract_url_from_text(raw_text: str) -> str:
        """Trích xuất URL douyin từ văn bản người dùng nhập (kể cả khi dính caption)."""
        pattern = r"(https?://[a-zA-Z0-9.-]*douyin\.com/[^\s,，。]+)"
        match = re.search(pattern, raw_text)
        if not match:
            raise ValueError("Không tìm thấy đường link Douyin hợp lệ trong nội dung bạn cung cấp.")
        return match.group(1).strip()

    @staticmethod
    async def resolve_item_id(url: str) -> Tuple[str, str]:
        """Follow redirect nếu là link rút gọn và trích xuất item_id."""
        headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=12.0) as client:
            res = await client.get(url)
            final_url = str(res.url)

            # Tìm item_id từ URL chuyển hướng
            id_match = re.search(r"/video/(\d+)", final_url) or re.search(r"(\d{18,21})", final_url)
            if not id_match:
                # Thử tìm id trong chuỗi query hoặc path
                query_match = re.search(r"modal_id=(\d+)", final_url)
                if query_match:
                    return query_match.group(1), final_url
                raise ValueError("Không thể tìm thấy mã ID video từ đường link Douyin này.")
            return id_match.group(1), final_url

    @classmethod
    async def extract_no_watermark_video(cls, raw_input: str) -> VideoMetadataResponse:
        """Bóc tách toàn diện thông tin video Douyin và lấy link MP4 không logo."""
        clean_url = cls.extract_url_from_text(raw_input)
        item_id, final_url = await cls.resolve_item_id(clean_url)
        logger.info(f"Đã trích xuất item_id: {item_id} từ url: {clean_url}")

        # Thử lấy dữ liệu qua API V2 của iesdouyin
        data = await cls._fetch_via_api_v2(item_id)
        if not data:
            data = await cls._fetch_via_web_detail(item_id)

        if not data:
            raise ValueError("Video này có thể đã bị xóa, đặt ở chế độ riêng tư hoặc Douyin giới hạn truy cập.")

        return cls._parse_aweme_data(item_id, data)

    @classmethod
    async def _fetch_via_api_v2(cls, item_id: str) -> Optional[dict]:
        """Truy vấn qua endpoint API V2 chính thức cho mobile share."""
        api_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={item_id}"
        headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"}
        try:
            async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
                res = await client.get(api_url)
                if res.status_code == 200:
                    json_data = res.json()
                    item_list = json_data.get("item_list", [])
                    if item_list and len(item_list) > 0:
                        return item_list[0]
        except Exception as e:
            logger.warning(f"Lỗi khi gọi API V2 Douyin: {e}")
        return None

    @classmethod
    async def _fetch_via_web_detail(cls, item_id: str) -> Optional[dict]:
        """Fallback qua Web API Detail của Douyin."""
        api_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={item_id}"
        headers = {"User-Agent": DESKTOP_UA, "Referer": f"https://www.douyin.com/video/{item_id}"}
        try:
            async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
                res = await client.get(api_url)
                if res.status_code == 200:
                    json_data = res.json()
                    aweme_detail = json_data.get("aweme_detail")
                    if aweme_detail:
                        return aweme_detail
        except Exception as e:
            logger.warning(f"Lỗi khi gọi Web API Detail: {e}")
        return None

    @classmethod
    def _parse_aweme_data(cls, item_id: str, item: dict) -> VideoMetadataResponse:
        """Trích xuất và chuẩn hóa metadata không logo."""
        desc = item.get("desc", "Video Douyin").strip()
        author_data = item.get("author", {})
        nickname = author_data.get("nickname", "Douyin Creator")
        avatar_list = author_data.get("avatar_thumb", {}).get("url_list", [])
        avatar = avatar_list[0] if avatar_list else None
        uid = str(author_data.get("uid") or author_data.get("short_id") or "")

        video_data = item.get("video", {})
        duration_ms = video_data.get("duration", 0)
        duration_sec = round(duration_ms / 1000.0, 2) if duration_ms > 0 else 0.0

        cover_list = video_data.get("cover", {}).get("url_list", [])
        cover_url = cover_list[0] if cover_list else None

        play_addr_list = video_data.get("play_addr", {}).get("url_list", [])
        raw_play_url = play_addr_list[0] if play_addr_list else ""

        # Thay thế watermark /playwm/ -> /play/ để lấy video không logo
        no_watermark_url = raw_play_url.replace("/playwm/", "/play/") if raw_play_url else ""

        music_data = item.get("music", {})
        music_url_list = music_data.get("play_url", {}).get("url_list", [])
        music_url = music_url_list[0] if music_url_list else None

        return VideoMetadataResponse(
            item_id=item_id,
            title=desc,
            duration=duration_sec,
            video_url=no_watermark_url,
            cover_url=cover_url,
            music_url=music_url,
            author=VideoAuthorInfo(nickname=nickname, avatar=avatar, uid=uid),
            source_platform="douyin",
        )

