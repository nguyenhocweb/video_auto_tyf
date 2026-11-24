import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

from src.core.config import settings

logger = logging.getLogger("facebook_reels_publisher")


class FacebookReelsPublisher:
    """
    Engine đăng video ngắn (Reels) tự động lên Facebook Page qua Meta Graph API v20.0+.
    Hỗ trợ luồng 3 bước chuẩn của Meta:
    1. upload_phase = start  -> Lấy video_id và upload_url
    2. Stream upload binary bytes lên máy chủ Facebook
    3. upload_phase = finish -> Xuất bản (PUBLISHED) kèm tiêu đề & hashtag
    """

    GRAPH_API_VERSION = "v20.0"
    GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    @classmethod
    def _get_page_credentials(
        cls, page_id: Optional[str] = None, access_token: Optional[str] = None
    ) -> tuple[str, str]:
        """Lấy Page ID và Page Access Token (ưu tiên tham số truyền vào, fallback về .env)."""
        pid = page_id or getattr(settings, "FB_PAGE_ID", "").strip()
        token = access_token or getattr(settings, "FB_PAGE_ACCESS_TOKEN", "").strip()

        if not pid or not token:
            raise ValueError(
                "Thiếu thông tin FB_PAGE_ID hoặc FB_PAGE_ACCESS_TOKEN. "
                "Vui lòng kiểm tra lại cấu hình trong file .env."
            )
        return pid, token

    @classmethod
    async def publish_reel_from_file(
        cls,
        video_path: str,
        caption: str = "",
        page_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Tự động đăng file video MP4 cục bộ lên Facebook Reels."""
        pid, token = cls._get_page_credentials(page_id, access_token)
        path_obj = Path(video_path)

        if not path_obj.exists():
            raise FileNotFoundError(f"Không tìm thấy file video tại: {video_path}")

        file_size = path_obj.stat().st_size
        logger.info(f"Bắt đầu quy trình đăng Reel lên Page [{pid}], kích thước video: {file_size} bytes")

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Bước 1: Khởi tạo phiên Upload (upload_phase = start)
            start_url = f"{cls.GRAPH_API_BASE}/{pid}/video_reels"
            start_res = await client.post(
                start_url,
                data={
                    "upload_phase": "start",
                    "access_token": token,
                },
            )

            if start_res.status_code != 200:
                err_body = start_res.text
                logger.error(f"Lỗi khởi tạo Reel session: {err_body}")
                raise RuntimeError(f"Facebook API Start Error: {err_body}")

            start_data = start_res.json()
            video_id = start_data.get("video_id")
            upload_url = start_data.get("upload_url")

            if not video_id or not upload_url:
                raise RuntimeError(f"Không nhận được video_id hoặc upload_url: {start_data}")

            logger.info(f"Đã tạo Reel session: video_id={video_id}")

            # Bước 2: Stream upload binary bytes lên upload_url
            with open(path_obj, "rb") as f:
                video_bytes = f.read()

            upload_headers = {
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            }

            upload_res = await client.post(
                upload_url,
                headers=upload_headers,
                content=video_bytes,
            )

            if upload_res.status_code not in [200, 201]:
                err_body = upload_res.text
                logger.error(f"Lỗi tải video lên máy chủ Facebook: {err_body}")
                raise RuntimeError(f"Facebook Video Upload Error: {err_body}")

            logger.info(f"Tải video lên Facebook thành công cho video_id={video_id}")

            # Bước 3: Xuất bản Reel (upload_phase = finish)
            finish_res = await client.post(
                start_url,
                data={
                    "upload_phase": "finish",
                    "access_token": token,
                    "video_id": video_id,
                    "video_state": "PUBLISHED",
                    "description": caption,
                },
            )

            if finish_res.status_code != 200:
                err_body = finish_res.text
                logger.error(f"Lỗi xuất bản Reel: {err_body}")
                raise RuntimeError(f"Facebook Reel Finish Error: {err_body}")

            finish_data = finish_res.json()
            logger.info(f"Đã gửi lệnh xuất bản Facebook Reel! Video ID: {video_id}")

            # Bước 4: Kiểm tra trạng thái xử lý ban đầu từ máy chủ Meta
            meta_status = "processing"
            try:
                chk = await client.get(
                    f"{cls.GRAPH_API_BASE}/{video_id}",
                    params={"fields": "status,published", "access_token": token},
                )
                if chk.status_code == 200:
                    meta_status = chk.json().get("status", {}).get("video_status", "processing")
            except Exception:
                pass

            return {
                "success": True,
                "video_id": video_id,
                "page_id": pid,
                "page_name": getattr(settings, "FB_PAGE_NAME", "Fanpage"),
                "caption": caption,
                "reel_url": f"https://www.facebook.com/reel/{video_id}",
                "meta_status": meta_status,
                "raw_response": finish_data,
            }

    @classmethod
    async def get_managed_pages(
        cls, user_token: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        """Lấy danh sách tất cả các Trang Facebook mà tài khoản có quyền quản trị."""
        u_token = user_token or getattr(settings, "FB_USER_ACCESS_TOKEN", "").strip()
        pages = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            if u_token:
                try:
                    url = f"{cls.GRAPH_API_BASE}/me/accounts"
                    params = {
                        "fields": "id,name,category,picture{url},fan_count,followers_count,access_token",
                        "access_token": u_token,
                    }
                    res = await client.get(url, params=params)
                    if res.status_code == 200:
                        data = res.json().get("data", [])
                        for item in data:
                            pages.append({
                                "id": str(item.get("id")),
                                "name": item.get("name", "Fanpage"),
                                "category": item.get("category", "General"),
                                "picture_url": item.get("picture", {}).get("data", {}).get("url", ""),
                                "fan_count": item.get("fan_count", 0),
                                "followers_count": item.get("followers_count", 0),
                                "access_token": item.get("access_token", ""),
                            })
                        if pages:
                            return pages
                except Exception as ex:
                    logger.warning(f"Lỗi truy vấn me/accounts với user_token: {ex}")

            # Fallback lấy từ cấu hình Page Token vĩnh viễn trong .env
            pid = getattr(settings, "FB_PAGE_ID", "").strip()
            p_token = getattr(settings, "FB_PAGE_ACCESS_TOKEN", "").strip()
            if pid and p_token:
                try:
                    res = await client.get(
                        f"{cls.GRAPH_API_BASE}/me",
                        params={
                            "fields": "id,name,category,picture{url},fan_count,followers_count",
                            "access_token": p_token,
                        },
                    )
                    if res.status_code == 200:
                        item = res.json()
                        pages.append({
                            "id": str(item.get("id", pid)),
                            "name": item.get("name", getattr(settings, "FB_PAGE_NAME", "Fanpage")),
                            "category": item.get("category", "General"),
                            "picture_url": item.get("picture", {}).get("data", {}).get("url", ""),
                            "fan_count": item.get("fan_count", 0),
                            "followers_count": item.get("followers_count", 0),
                            "access_token": p_token,
                        })
                except Exception as ex:
                    logger.error(f"Fallback get page info thất bại: {ex}")
        return pages

    @classmethod
    async def get_page_videos(
        cls, page_id: str, access_token: Optional[str] = None, limit: int = 25
    ) -> list[Dict[str, Any]]:
        """Lấy danh sách video/Reels của Fanpage kèm lượt views, likes, comments."""
        _, token = cls._get_page_credentials(page_id, access_token)
        url = f"{cls.GRAPH_API_BASE}/{page_id}/videos"
        params = {
            "fields": "id,title,description,created_time,picture,permalink_url,length,views,likes.summary(true),comments.summary(true)",
            "limit": limit,
            "access_token": token,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(url, params=params)
            if res.status_code != 200:
                logger.error(f"Lỗi lấy videos của page [{page_id}]: {res.text}")
                return []
            raw_list = res.json().get("data", [])
            results = []
            for item in raw_list:
                likes_cnt = item.get("likes", {}).get("summary", {}).get("total_count", 0)
                reac_cnt = item.get("reactions", {}).get("summary", {}).get("total_count", 0)
                vid_id = item.get("id")
                results.append({
                    "id": vid_id, "title": item.get("title") or item.get("description", "")[:60],
                    "description": item.get("description", ""), "created_time": item.get("created_time"),
                    "thumbnail": item.get("picture", ""), "length": item.get("length", 0), "views": item.get("views", 0),
                    "permalink_url": f"https://www.facebook.com/reel/{vid_id}" if vid_id else (item.get("permalink_url") or ""),
                    "reactions_count": likes_cnt or reac_cnt,
                    "comments_count": item.get("comments", {}).get("summary", {}).get("total_count", 0),
                })
            return results

    @classmethod
    async def get_page_posts(
        cls, page_id: str, access_token: Optional[str] = None, limit: int = 25
    ) -> list[Dict[str, Any]]:
        """Lấy danh sách bài viết đã xuất bản kèm số like, comment, share."""
        _, token = cls._get_page_credentials(page_id, access_token)
        params = {
            "fields": "id,message,created_time,full_picture,permalink_url,shares,reactions.summary(total_count),comments.summary(total_count)",
            "limit": limit, "access_token": token,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(f"{cls.GRAPH_API_BASE}/{page_id}/feed", params=params)
            if res.status_code != 200:
                res = await client.get(f"{cls.GRAPH_API_BASE}/{page_id}/posts", params=params)
            if res.status_code != 200:
                logger.error(f"Lỗi lấy posts của page [{page_id}]: {res.text}")
                return []
            raw_list = res.json().get("data", [])
            results = []
            for item in raw_list:
                pid_val = item.get("id")
                results.append({
                    "id": pid_val, "message": item.get("message", ""), "created_time": item.get("created_time"),
                    "thumbnail": item.get("full_picture", ""), "shares_count": item.get("shares", {}).get("count", 0) if item.get("shares") else 0,
                    "permalink_url": f"https://www.facebook.com/reel/{pid_val}" if pid_val else (item.get("permalink_url") or ""),
                    "reactions_count": item.get("reactions", {}).get("summary", {}).get("total_count", 0),
                    "comments_count": item.get("comments", {}).get("summary", {}).get("total_count", 0),
                })
            return results

    @classmethod
    async def get_reel_status(
        cls, video_id: str, access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Kiểm tra trạng thái xử lý video trên máy chủ Facebook."""
        _, token = cls._get_page_credentials(access_token=access_token)
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{cls.GRAPH_API_BASE}/{video_id}",
                params={"fields": "status,published", "access_token": token},
            )
            return res.json()

