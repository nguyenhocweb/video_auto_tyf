import re
import logging
from typing import Tuple, Optional
import httpx

logger = logging.getLogger("douyin_url_resolver")

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)


class DouyinUrlResolver:
    """Helper bóc tách và phân giải đường link kênh / video Douyin."""

    @staticmethod
    def extract_url(raw_text: str) -> str:
        """Trích xuất URL kênh hoặc video từ nội dung người dùng nhập."""
        pattern = r"(https?://[a-zA-Z0-9.-]*douyin\.com/[^\s,，。]+)"
        match = re.search(pattern, raw_text)
        if not match:
            raise ValueError("Không tìm thấy đường link Douyin hợp lệ.")
        return match.group(1).strip()

    @staticmethod
    def parse_user_sec_uid(url: str) -> Optional[str]:
        """Trích xuất và kiểm tra tính hợp lệ của sec_uid từ URL kênh /user/..."""
        if "/user/" in url:
            sec_match = re.search(r"/user/([a-zA-Z0-9_\-]+)", url)
            sec_uid = sec_match.group(1) if sec_match else None
            if sec_uid and len(sec_uid) < 35:
                raise ValueError(
                    f"Đường link kênh Douyin này bị thiếu ký tự ở đuôi "
                    f"(mã tác giả chỉ có {len(sec_uid)} ký tự, chuẩn thường trên 50 ký tự). "
                    f"Bạn hãy copy đầy đủ link kênh từ trình duyệt, hoặc dán link 1 video bất kỳ của kênh này để hệ thống tự động nhận diện nhé!"
                )
            return sec_uid
        return None

    @classmethod
    async def resolve_channel_url(cls, raw_input: str) -> Tuple[str, Optional[str]]:
        """
        Chuẩn hóa đường link thành link kênh cá nhân (/user/...).
        Trả về tuple (channel_url, sec_uid).
        """
        clean_url = cls.extract_url(raw_input)

        # 1. Nếu là link kênh (/user/...)
        sec_uid = cls.parse_user_sec_uid(clean_url)
        if sec_uid:
            # Chuẩn hóa triệt để: Gọt sạch toàn bộ query params (?vid=..., &relation=...) để chống lọt modal video cũ!
            canonical_user_url = f"https://www.douyin.com/user/{sec_uid}"
            return canonical_user_url, sec_uid

        # 2. Nếu là link rút gọn (v.douyin.com) hoặc video (douyin.com/video/...)
        headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=12.0) as client:
            res = await client.get(clean_url)
            final_url = str(res.url)

            # Nếu sau redirect ra link user
            if "/user/" in final_url:
                sec_match = re.search(r"/user/([a-zA-Z0-9_\-]+)", final_url)
                sec_uid = sec_match.group(1) if sec_match else None
                return f"https://www.douyin.com/user/{sec_uid}", sec_uid

            # Nếu là link video, bóc tách sec_uid tác giả từ HTML trang hoặc API
            id_match = re.search(r"/video/(\d+)", final_url) or re.search(r"modal_id=(\d+)", final_url)
            if id_match:
                html_body = res.text
                sec_in_html = re.search(r'["\']sec_uid["\']\s*:\s*["\'](MS4wLjABAAAA[a-zA-Z0-9_\-]+)["\']', html_body)
                if not sec_in_html:
                    sec_in_html = re.search(r'/user/(MS4wLjABAAAA[a-zA-Z0-9_\-]+)', html_body)
                if sec_in_html:
                    author_sec_uid = sec_in_html.group(1)
                    return f"https://www.douyin.com/user/{author_sec_uid}", author_sec_uid

                item_id = id_match.group(1)
                try:
                    api_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={item_id}"
                    item_res = await client.get(api_url)
                    if item_res.status_code == 200:
                        items = item_res.json().get("item_list", [])
                        if items and items[0].get("author", {}).get("sec_uid"):
                            author_sec_uid = items[0]["author"]["sec_uid"]
                            return f"https://www.douyin.com/user/{author_sec_uid}", author_sec_uid
                except Exception as api_err:
                    logger.debug(f"Không lấy được author sec_uid qua API: {api_err}")

        # Fallback giữ nguyên clean_url
        return clean_url, None
