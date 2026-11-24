import hmac
import hashlib
import base64
import json
import time
from typing import Dict, Any, Optional
from src.core.config import settings

JWT_SECRET = getattr(settings, "JWT_SECRET", "video_ai_secure_jwt_secret_key_2026_super_safe")
SALT = "video_ai_password_salt_2026"

ACCESS_TOKEN_EXPIRE_SECONDS = getattr(settings, "ACCESS_TOKEN_EXPIRE_SECONDS", 86400 * 7)  # 7 ngày cho Access Token
REFRESH_TOKEN_EXPIRE_SECONDS = 86400 * 30  # 30 ngày cho Refresh Token


def hash_password(password: str) -> str:
    """Băm mật khẩu người dùng chuẩn PBKDF2-HMAC-SHA256."""
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        SALT.encode("utf-8"),
        iterations=100000,
    )
    return key.hex()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """So sánh mật khẩu dạng an toàn chống tấn công timing-attack."""
    computed = hash_password(plain_password)
    return hmac.compare_digest(computed, hashed_password)


def _generate_jwt(payload_data: Dict[str, Any], expires_seconds: int) -> str:
    """Hàm lõi ký JWT HS256."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload_data)
    payload["exp"] = int(time.time()) + expires_seconds
    payload["iat"] = int(time.time())

    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signing_input = f"{h_b64}.{p_b64}"

    signature = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{signing_input}.{sig_b64}"


def _verify_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Hàm lõi kiểm tra chữ ký và hạn dùng JWT."""
    parts = token.split(".")
    if len(parts) != 3:
        return None

    signing_input = f"{parts[0]}.{parts[1]}"
    signature = hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest()
    expected_sig = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    if not hmac.compare_digest(expected_sig, parts[2]):
        return None

    rem = len(parts[1]) % 4
    pad = parts[1] + "=" * (4 - rem if rem else 0)
    try:
        payload = json.loads(base64.urlsafe_b64decode(pad).decode())
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def create_access_token(data: Dict[str, Any], expires_delta_seconds: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
    """Tạo Access Token chứa vai trò (role) để phân quyền hệ thống."""
    payload = dict(data)
    payload["token_type"] = "access"
    return _generate_jwt(payload, expires_delta_seconds)


def create_refresh_token(data: Dict[str, Any], expires_delta_seconds: int = REFRESH_TOKEN_EXPIRE_SECONDS) -> str:
    """Tạo Refresh Token dài hạn dùng để cấp lại Access Token mới."""
    payload = dict(data)
    payload["token_type"] = "refresh"
    return _generate_jwt(payload, expires_delta_seconds)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Giải mã Access Token và xác thực loại token."""
    payload = _verify_jwt(token)
    if not payload:
        return None
    # Cho phép tương thích ngược nếu chưa có trường token_type
    if payload.get("token_type") and payload.get("token_type") != "access":
        return None
    return payload


def decode_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    """Giải mã Refresh Token và xác thực loại token."""
    payload = _verify_jwt(token)
    if not payload or payload.get("token_type") != "refresh":
        return None
    return payload
