import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any
from src.core.config import settings

logger = logging.getLogger("video_aspect_converter")


class VideoAspectConverter:
    """Tiện ích kiểm tra và chuyển đổi video dọc (9:16) sang chuẩn 16:9 ngang cho YouTube Video dài."""

    @staticmethod
    def get_video_dimensions(video_path: str) -> Dict[str, Any]:
        """Lấy kích thước và thời lượng video bằng ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration",
                "-of", "json", video_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                streams = data.get("streams", [])
                if streams:
                    w = int(streams[0].get("width") or 0)
                    h = int(streams[0].get("height") or 0)
                    dur = float(streams[0].get("duration") or 0.0)
                    return {"width": w, "height": h, "duration": dur, "is_vertical": (w <= h)}
        except Exception as ex:
            logger.warning(f"Lỗi đọc metadata video bằng ffprobe: {ex}")
        return {"width": 0, "height": 0, "duration": 0.0, "is_vertical": False}

    @classmethod
    def ensure_horizontal_16_9(cls, video_path: str) -> str:
        """
        Nếu video là video dọc hoặc vuông (width <= height), chuyển đổi sang khung hình 16:9 (1920x1080)
        với hiệu ứng nền mờ (Blurred Background) điện ảnh 2 bên.
        Điều này đảm bảo 100% YouTube nhận diện là Video Dài/Thường, không bị biến thành Shorts.
        """
        p = Path(video_path)
        if not p.exists():
            return video_path

        info = cls.get_video_dimensions(video_path)
        w, h = info["width"], info["height"]

        # Nếu đã là video ngang chuẩn (chiều rộng lớn hơn chiều cao rõ rệt), giữ nguyên
        if w > 0 and h > 0 and (w / h) >= 1.4:
            logger.info(f"Video {p.name} đã là video ngang ({w}x{h}). Không cần chuyển đổi.")
            return video_path

        temp_dir = settings.TEMP_DIR / "youtube_converted"
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = temp_dir / f"h169_{p.stem}.mp4"

        logger.info(f"Đang chuyển đổi video dọc {p.name} ({w}x{h}) sang 16:9 ngang (1920x1080)...")
        cmd = [
            "ffmpeg", "-y", "-i", str(p),
            "-filter_complex",
            "[0:v]scale=192:108:force_original_aspect_ratio=increase,crop=192:108,boxblur=5:5,scale=1920:1080:flags=fast_bilinear[bg];"
            "[0:v]scale=-1:1080[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]",
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-threads", "0", "-c:a", "copy",
            str(output_path),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                logger.info(f"Chuyển đổi 16:9 thành công: {output_path.name}")
                return str(output_path)
            logger.warning(f"FFmpeg chuyển 16:9 thất bại: {res.stderr[:300]}. Sử dụng file gốc.")
        except Exception as ex:
            logger.error(f"Lỗi khi thực thi FFmpeg chuyển 16:9: {ex}")

        return video_path

    @classmethod
    def ensure_vertical_9_16(cls, video_path: str) -> str:
        """
        Nếu video KHÔNG PHẢI là video dọc 9:16 (ví dụ video ngang 16:9, vuông 1:1, hoặc 4:3),
        chuyển đổi sang khung hình 9:16 (1080x1920) với hiệu ứng nền mờ (Blurred Background).
        Điều này đảm bảo 100% YouTube nhận diện là Shorts khi người dùng chọn chế độ Shorts,
        tránh việc bị YouTube phân loại thành Video dài (Regular video) do sai tỷ lệ khung hình.
        """
        p = Path(video_path)
        if not p.exists():
            return video_path

        info = cls.get_video_dimensions(video_path)
        w, h = info["width"], info["height"]

        # Tỷ lệ 9:16 chuẩn là 9 / 16 = 0.5625
        # Nếu đã là video dọc chuẩn (w/h nằm trong khoảng 0.50 đến 0.62), giữ nguyên
        if w > 0 and h > 0:
            ratio = w / h
            if 0.50 <= ratio <= 0.62:
                logger.info(f"Video {p.name} đã là video dọc chuẩn 9:16 ({w}x{h}, ratio={ratio:.3f}). Không cần chuyển đổi.")
                return video_path

        temp_dir = settings.TEMP_DIR / "youtube_converted"
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = temp_dir / f"v916_{p.stem}.mp4"

        logger.info(f"Đang chuyển đổi video {p.name} ({w}x{h}) sang 9:16 dọc chuẩn YouTube Shorts (1080x1920)...")
        cmd = [
            "ffmpeg", "-y", "-i", str(p),
            "-filter_complex",
            "[0:v]scale=108:192:force_original_aspect_ratio=increase,crop=108:192,boxblur=5:5,scale=1080:1920:flags=fast_bilinear[bg];"
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]",
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-threads", "0", "-c:a", "copy",
            str(output_path),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                logger.info(f"Chuyển đổi 9:16 Shorts thành công: {output_path.name}")
                return str(output_path)
            logger.warning(f"FFmpeg chuyển 9:16 thất bại: {res.stderr[:300]}. Sử dụng file gốc.")
        except Exception as ex:
            logger.error(f"Lỗi khi thực thi FFmpeg chuyển 9:16: {ex}")

        return video_path
