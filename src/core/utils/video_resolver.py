import os
import re
import logging
from pathlib import Path
from typing import Optional
import httpx

from src.core.config import settings

logger = logging.getLogger("video_resolver")


async def resolve_local_video_path(video_input: str) -> str:
    """
    Chuẩn hóa đường dẫn video thành file cục bộ hợp lệ trên máy chủ.
    Hỗ trợ: đường dẫn tuyệt đối, tên file, relative static path, hoặc URL (Cloudinary).
    """
    if not video_input or not str(video_input).strip():
        raise ValueError("Đường dẫn video không được để trống.")

    raw_path = str(video_input).strip()

    # 1. Nếu đã là đường dẫn file hợp lệ tồn tại trên máy
    p = Path(raw_path)
    if p.exists() and p.is_file():
        return str(p.resolve())

    # 2. Xử lý tên file (VD: final_6af3...mp4 hoặc /static/dubbing/final_...mp4)
    # Lấy tên file gốc
    clean_name = raw_path.replace("\\", "/").split("/")[-1].split("?")[0]

    # Kiểm tra trong DUBBING_OUTPUT_DIR
    in_dubbing = settings.DUBBING_OUTPUT_DIR / clean_name
    if in_dubbing.exists() and in_dubbing.is_file():
        return str(in_dubbing.resolve())

    # Kiểm tra trong TEMP_DIR
    in_temp = settings.TEMP_DIR / clean_name
    if in_temp.exists() and in_temp.is_file():
        return str(in_temp.resolve())

    # Kiểm tra trong AUDIO_OUTPUT_DIR
    in_media = settings.AUDIO_OUTPUT_DIR / clean_name
    if in_media.exists() and in_media.is_file():
        return str(in_media.resolve())

    # 3. Nếu là đường dẫn Web URL (Cloudinary hoặc máy chủ khác)
    if raw_path.startswith("http://") or raw_path.startswith("https://"):
        cache_dir = settings.TEMP_DIR / "publish_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_file = cache_dir / clean_name

        if cached_file.exists() and cached_file.stat().st_size > 1024:
            return str(cached_file.resolve())

        logger.info(f"Đang tải video từ URL về bộ nhớ tạm để xuất bản: {raw_path}")
        async with httpx.AsyncClient(timeout=180.0) as client:
            res = await client.get(raw_path)
            if res.status_code == 200:
                cached_file.write_bytes(res.content)
                logger.info(f"Tải video thành công ({len(res.content)} bytes): {cached_file}")
                return str(cached_file.resolve())
            raise RuntimeError(f"Không thể tải video từ URL ({res.status_code}): {raw_path}")

    raise FileNotFoundError(f"Không tìm thấy file video tại: {video_input}")
