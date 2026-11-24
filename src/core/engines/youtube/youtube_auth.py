import os
import logging
import urllib.parse
from typing import Dict, Any, Optional
import httpx
from src.core.config import settings

logger = logging.getLogger("youtube_auth")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/youtube/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/userinfo.email",
]


class YouTubeAuthHelper:
    """Helper chuyên trách xử lý ủy quyền Google OAuth 2.0 và quản lý Token."""

    @staticmethod
    def get_auth_url(state: Optional[str] = None) -> str:
        """Tạo đường link xác thực OAuth 2.0 (access_type=offline để lấy refresh_token vĩnh viễn)."""
        client_id = getattr(settings, "YOUTUBE_CLIENT_ID", "").strip()
        redirect_uri = getattr(settings, "YOUTUBE_REDIRECT_URI", "").strip()
        if not client_id:
            raise ValueError("Thiếu cấu hình YOUTUBE_CLIENT_ID trong .env")

        scope_str = " ".join(SCOPES)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state
        return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    @staticmethod
    async def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
        """Đổi mã Authorization Code lấy access_token và refresh_token vĩnh viễn."""
        client_id = getattr(settings, "YOUTUBE_CLIENT_ID", "").strip()
        client_secret = getattr(settings, "YOUTUBE_CLIENT_SECRET", "").strip()
        redirect_uri = getattr(settings, "YOUTUBE_REDIRECT_URI", "").strip()

        payload = {
            "code": code.strip(),
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(TOKEN_URL, data=payload)
            if res.status_code != 200:
                raise ValueError(f"Google OAuth Error: {res.text}")
            return res.json()

    @staticmethod
    async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
        """Dùng refresh_token vĩnh viễn để tự động cấp mới access_token."""
        client_id = getattr(settings, "YOUTUBE_CLIENT_ID", "").strip()
        client_secret = getattr(settings, "YOUTUBE_CLIENT_SECRET", "").strip()

        payload = {
            "refresh_token": refresh_token.strip(),
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(TOKEN_URL, data=payload)
            if res.status_code != 200:
                raise ValueError(f"Google Refresh Error: {res.text}")
            return res.json()

    @staticmethod
    async def get_my_channel(access_token: str) -> Dict[str, Any]:
        """Lấy thông tin kênh YouTube chính chủ (Tên kênh, Avatar, Số người đăng ký)."""
        headers = {"Authorization": f"Bearer {access_token.strip()}"}
        url = f"{API_BASE}/channels?part=snippet,statistics&mine=true"

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                raise ValueError(f"Lỗi lấy thông tin kênh YouTube: {res.text}")
            data = res.json()
            items = data.get("items", [])
            if not items:
                raise ValueError("Không tìm thấy kênh YouTube nào gắn với tài khoản này.")

            item = items[0]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            thumbnails = snippet.get("thumbnails", {})

            return {
                "channel_id": item.get("id"),
                "title": snippet.get("title"),
                "custom_url": snippet.get("customUrl"),
                "avatar_url": (
                    thumbnails.get("default", {}).get("url")
                    or thumbnails.get("medium", {}).get("url")
                ),
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
            }

    @staticmethod
    async def get_google_user_email(access_token: str) -> Optional[str]:
        """Lấy địa chỉ Gmail/Google Account của người dùng sở hữu token qua UserInfo endpoint."""
        headers = {"Authorization": f"Bearer {access_token.strip()}"}
        url = "https://www.googleapis.com/oauth2/v3/userinfo"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("email")
                logger.warning(f"Không thể lấy email Google UserInfo: {res.text}")
        except Exception as e:
            logger.warning(f"Lỗi gọi Google UserInfo API: {e}")
        return None
