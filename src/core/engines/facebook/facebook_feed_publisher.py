import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

from src.core.config import settings

logger = logging.getLogger("facebook_feed_publisher")


class FacebookFeedPublisher:
    """
    Engine xuất bản video thông thường (Feed Post / Video bài viết)
    lên Facebook Fanpage qua Meta Graph API v20.0.
    """

    GRAPH_API_VERSION = "v20.0"
    GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    @classmethod
    def _get_page_credentials(
        cls, page_id: Optional[str] = None, access_token: Optional[str] = None
    ) -> tuple[str, str]:
        pid = page_id or getattr(settings, "FB_PAGE_ID", "").strip()
        token = access_token or getattr(settings, "FB_PAGE_ACCESS_TOKEN", "").strip()
        if not pid or not token:
            raise ValueError(
                "Thiếu thông tin FB_PAGE_ID hoặc FB_PAGE_ACCESS_TOKEN. "
                "Vui lòng kiểm tra lại cấu hình Fanpage."
            )
        return pid, token

    @classmethod
    async def publish_feed_video(
        cls,
        video_path: str,
        caption: str = "",
        title: str = "",
        page_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Tải file video lên Fanpage và đăng dưới dạng Bài viết video thông thường."""
        pid, token = cls._get_page_credentials(page_id, access_token)
        path_obj = Path(video_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Không tìm thấy file video tại: {video_path}")

        file_size = path_obj.stat().st_size
        logger.info(
            f"Bắt đầu xuất bản Bài viết video lên Page [{pid}], dung lượng {file_size} bytes"
        )

        url = f"https://graph-video.facebook.com/{cls.GRAPH_API_VERSION}/{pid}/videos"
        async with httpx.AsyncClient(timeout=180.0) as client:
            with open(path_obj, "rb") as f:
                files = {"source": (path_obj.name, f, "video/mp4")}
                data = {
                    "description": caption,
                    "title": title or (caption[:60] if caption else "Video"),
                    "published": "true",
                    "access_token": token,
                }
                res = await client.post(url, data=data, files=files)

                # Nếu graph-video gặp vấn đề (VD: mạng/DNS), thử qua endpoint tiêu chuẩn
                if res.status_code not in [200, 201]:
                    logger.warning(
                        f"Lỗi gửi qua graph-video: {res.text}. Thử gửi qua graph.facebook.com..."
                    )
                    f.seek(0)
                    fallback_url = f"{cls.GRAPH_API_BASE}/{pid}/videos"
                    res = await client.post(fallback_url, data=data, files=files)

            if res.status_code not in [200, 201]:
                err_body = res.text
                logger.error(f"Lỗi xuất bản Bài viết video Facebook: {err_body}")
                raise RuntimeError(f"Facebook Feed Video Error: {err_body}")

            res_data = res.json()
            video_id = str(res_data.get("id", ""))
            logger.info(f"Đã xuất bản thành công Bài viết video! ID: {video_id}")

            return {
                "success": True,
                "video_id": video_id,
                "page_id": pid,
                "page_name": getattr(settings, "FB_PAGE_NAME", "Fanpage"),
                "caption": caption,
                "post_url": f"https://www.facebook.com/{video_id}",
                "post_type": "feed",
                "raw_response": res_data,
            }
