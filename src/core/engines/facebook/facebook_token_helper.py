import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import httpx

from src.core.config import settings

logger = logging.getLogger("facebook_token_helper")


class FacebookTokenHelper:
    """Xử lý kiểm tra, gia hạn và nâng cấp User Access Token sang Long-Lived Token (60 ngày)."""

    GRAPH_API_VERSION = "v20.0"
    GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    @classmethod
    async def exchange_to_long_lived_token(
        cls, short_lived_token: str
    ) -> Dict[str, Any]:
        """Đổi Short-lived User Token (1 giờ) lấy Long-lived User Token (60 ngày)."""
        app_id = getattr(settings, "FB_APP_ID", "").strip()
        app_secret = getattr(settings, "FB_APP_SECRET", "").strip()

        if not app_id or not app_secret:
            raise ValueError("Thiếu FB_APP_ID hoặc FB_APP_SECRET trong cấu hình.")

        url = f"{cls.GRAPH_API_BASE}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token.strip(),
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(url, params=params)
            if res.status_code != 200:
                err_text = res.text
                logger.error(f"Lỗi đổi Long-Lived Token: {err_text}")
                raise ValueError(f"Meta Graph API Error: {err_text}")

            data = res.json()
            long_lived_token = data.get("access_token")
            expires_in = data.get("expires_in", 5184000)  # ~60 ngày (giây)

            return {
                "access_token": long_lived_token,
                "expires_in": expires_in,
                "expires_days": round(expires_in / 86400, 1),
            }

    @classmethod
    async def inspect_token(cls, token: Optional[str] = None) -> Dict[str, Any]:
        """Kiểm tra tính hợp lệ và thời hạn sống của Access Token."""
        t = token or getattr(settings, "FB_USER_ACCESS_TOKEN", "").strip()
        app_id = getattr(settings, "FB_APP_ID", "").strip()
        app_secret = getattr(settings, "FB_APP_SECRET", "").strip()

        if not t:
            return {"is_valid": False, "error": "Chưa có User Access Token"}

        app_access_token = f"{app_id}|{app_secret}"
        url = f"{cls.GRAPH_API_BASE}/debug_token"
        params = {"input_token": t, "access_token": app_access_token}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, params=params)
                if res.status_code != 200:
                    try:
                        err_json = res.json().get("error", {})
                        raw_msg = err_json.get("message", res.text)
                        if "API access blocked" in raw_msg:
                            clean_err = "Ứng dụng Meta (App) bị khóa quyền API. Vui lòng vào developers.facebook.com kiểm tra Data Use Checkup hoặc quyền tài khoản."
                        else:
                            clean_err = f"{raw_msg} (Mã lỗi: {err_json.get('code', res.status_code)})"
                    except Exception:
                        clean_err = res.text
                    return {"is_valid": False, "error": clean_err, "expires_at": None}
                data = res.json().get("data", {})
                return {
                    "is_valid": data.get("is_valid", False),
                    "expires_at": data.get("expires_at", 0),
                    "data_access_expires_at": data.get("data_access_expires_at"),
                    "scopes": data.get("scopes", []),
                    "token_type": data.get("type", "USER"),
                    "error": data.get("error", {}).get("message") if not data.get("is_valid") else None,
                }
        except Exception as exc:
            logger.warning(f"Lỗi khi inspect token qua Graph API: {exc}")
            return {"is_valid": False, "error": f"Không thể kết nối Meta: {str(exc)}", "expires_at": None}

    @classmethod
    def save_user_token_to_env(cls, new_token: str) -> None:
        """Lưu User Token mới vào file be/.env và cập nhật settings runtime."""
        settings.FB_USER_ACCESS_TOKEN = new_token.strip()
        env_path = settings.BASE_DIR / ".env"
        if not env_path.exists():
            env_path = Path("be/.env")

        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "FB_USER_ACCESS_TOKEN=" in content:
                content = re.sub(
                    r'FB_USER_ACCESS_TOKEN=.*',
                    f'FB_USER_ACCESS_TOKEN="{new_token.strip()}"',
                    content,
                )
            else:
                content += f'\nFB_USER_ACCESS_TOKEN="{new_token.strip()}"\n'
            env_path.write_text(content, encoding="utf-8")
            logger.info("Đã cập nhật FB_USER_ACCESS_TOKEN vào file .env")

