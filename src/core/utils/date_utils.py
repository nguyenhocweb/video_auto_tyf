import datetime
from typing import Any, Optional

# Múi giờ chuẩn Việt Nam (UTC+7 / Asia/Ho_Chi_Minh)
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))


def get_vn_now() -> datetime.datetime:
    """Lấy thời gian thực hiện tại theo chuẩn múi giờ Việt Nam (UTC+7)."""
    return datetime.datetime.now(VN_TZ)


def to_vn_iso(dt_val: Any) -> str:
    """
    Chuyển đổi bất kỳ kiểu datetime/chuỗi từ MongoDB sang định dạng ISO có múi giờ Việt Nam (+07:00).
    Tự động bù +7 giờ nếu datetime từ MongoDB là UTC naive.
    """
    if not dt_val:
        return ""

    if isinstance(dt_val, str):
        s = dt_val.strip()
        if not s:
            return ""
        # Nếu chuỗi ISO chưa có Z hoặc offset, coi nó là UTC
        if not s.endswith("Z") and "+" not in s and "-" not in s[10:]:
            s += "Z"
        try:
            parsed = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
            return parsed.astimezone(VN_TZ).isoformat()
        except Exception:
            return s

    if isinstance(dt_val, datetime.datetime):
        if dt_val.tzinfo is None:
            # Naive datetime lưu trong MongoDB theo chuẩn UTC
            dt_val = dt_val.replace(tzinfo=datetime.timezone.utc)
        return dt_val.astimezone(VN_TZ).isoformat()

    return str(dt_val)


def format_vn_datetime(dt_val: Any, fmt: str = "%H:%M:%S %d/%m/%Y") -> str:
    """Định dạng thời gian thân thiện chuẩn Việt Nam (VD: 11:25:27 04/11/2026)."""
    if not dt_val:
        return "Chưa cập nhật"

    if isinstance(dt_val, str):
        s = dt_val.strip()
        if not s.endswith("Z") and "+" not in s and "-" not in s[10:]:
            s += "Z"
        try:
            parsed = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
            return parsed.astimezone(VN_TZ).strftime(fmt)
        except Exception:
            return s

    if isinstance(dt_val, datetime.datetime):
        if dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=datetime.timezone.utc)
        return dt_val.astimezone(VN_TZ).strftime(fmt)

    return str(dt_val)

