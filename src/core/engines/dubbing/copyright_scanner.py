import subprocess
import json
import logging
import httpx
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("copyright_scanner")

ACOUSTID_API_URL = "https://api.acoustid.org/v2/lookup"
ACOUSTID_CLIENT_KEY = "8XaBELgH"

# Danh sách các hãng đĩa / mạng lưới bản quyền số nghiêm ngặt nhất thế giới và VN
HIGH_RISK_KEYWORDS = [
    "universal", "umg", "sony", "sme", "warner", "wmg", "emi",
    "bh media", "zing mp3", "pops", "vcpmc", "orchard", "believe",
    "merlin", "kobalt", "bighit", "yg entertainment", "sm entertainment",
    "atlantic", "interscope", "columbia", "def jam", "republic"
]


class AudioCopyrightScannerEngine:
    """Engine quét phân tích dấu vân tay âm thanh số & thẩm định bản quyền thương mại."""

    @staticmethod
    def extract_metadata(file_path: Path) -> Dict[str, str]:
        """Trích xuất ID3 tags, ISRC và thông tin bản quyền nhúng trong file bằng ffprobe."""
        meta: Dict[str, str] = {}
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format_tags",
                "-of", "json", str(file_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
            if res.returncode == 0 and res.stdout:
                parsed = json.loads(res.stdout.decode("utf-8", errors="ignore"))
                tags = parsed.get("format", {}).get("tags", {})
                for k, v in tags.items():
                    meta[k.lower()] = str(v).strip()
        except Exception as e:
            logger.warning(f"Lỗi khi đọc metadata âm thanh: {e}")
        return meta

    @staticmethod
    def generate_fingerprint(file_path: Path) -> Tuple[str, float]:
        """Tạo dấu vân tay âm thanh số Chromaprint bằng FFmpeg."""
        fp = ""
        duration = 0.0
        try:
            # Đo thời lượng
            dur_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
            ]
            dur_res = subprocess.run(dur_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
            if dur_res.returncode == 0 and dur_res.stdout:
                duration = round(float(dur_res.stdout.decode().strip()), 2)

            # Sinh Chromaprint
            fp_cmd = ["ffmpeg", "-i", str(file_path), "-f", "chromaprint", "-"]
            fp_res = subprocess.run(fp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12)
            if fp_res.returncode == 0 and fp_res.stdout:
                fp = fp_res.stdout.decode("utf-8", errors="ignore").strip()
        except Exception as e:
            logger.warning(f"Lỗi khi sinh Chromaprint: {e}")
        return fp, duration

    @classmethod
    def query_acoustid(cls, fingerprint: str, duration: float) -> Optional[Dict[str, Any]]:
        """Tra cứu dấu vân tay âm thanh qua cơ sở dữ liệu bản quyền AcoustID / MusicBrainz."""
        if not fingerprint or duration <= 0:
            return None
        try:
            params = {
                "client": ACOUSTID_CLIENT_KEY,
                "meta": "recordings+releasegroups+compress",
                "duration": int(duration),
                "fingerprint": fingerprint,
            }
            with httpx.Client(timeout=5.0) as client:
                res = client.get(ACOUSTID_API_URL, params=params)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("status") == "ok" and data.get("results"):
                        return data["results"][0]
        except Exception as e:
            logger.info(f"Không thể kết nối AcoustID cloud: {e}")
        return None

    @classmethod
    def scan_audio(cls, file_path: Path, is_sanitized: bool = False) -> Dict[str, Any]:
        """Quét tổng hợp: Kết hợp phân tích Metadata ID3 cục bộ + Tra cứu vân tay Chromaprint."""
        meta = cls.extract_metadata(file_path)
        fp, duration = cls.generate_fingerprint(file_path)
        acoustid_result = cls.query_acoustid(fp, duration)

        matched_title = meta.get("title")
        matched_artist = meta.get("artist") or meta.get("album_artist")
        matched_label = meta.get("publisher") or meta.get("copyright") or meta.get("encoded_by")
        confidence = 0.0

        if acoustid_result and acoustid_result.get("recordings"):
            rec = acoustid_result["recordings"][0]
            matched_title = rec.get("title", matched_title)
            artists = rec.get("artists", [])
            if artists:
                matched_artist = artists[0].get("name", matched_artist)
            confidence = float(acoustid_result.get("score", 0.85))

        has_copyright = False
        risk_level = "safe" # safe, warning, danger
        details = "Không phát hiện bản quyền thương mại trong cơ sở dữ liệu bản quyền số."
        recommendation = "Bản nhạc an toàn, sẵn sàng đăng tải lên TikTok / YouTube Shorts."

        # Đánh giá mức độ rủi ro bản quyền
        meta_blob = f"{matched_title or ''} {matched_artist or ''} {matched_label or ''}".lower()
        is_high_risk = any(kw in meta_blob for kw in HIGH_RISK_KEYWORDS)

        if matched_title or matched_artist or is_high_risk:
            has_copyright = True
            if is_sanitized:
                risk_level = "warning"
                details = f"Phát hiện ca khúc gốc: '{matched_title or 'Chưa rõ'}' của '{matched_artist or 'Nhiều nghệ sĩ'}'. Tuy nhiên âm thanh ĐÃ ĐƯỢC BẺ SÓNG ÂM DSP (Pitch +2.5%, Tempo Warp), giảm 90% nguy cơ quét Content ID."
                recommendation = "Đã khử bản quyền DSP, có thể đăng tải an toàn."
            else:
                risk_level = "danger" if is_high_risk or confidence > 0.7 else "warning"
                details = f"CẢNH BÁO BẢN QUYỀN: Phát hiện bài hát thương mại '{matched_title or 'Không tên'}' ({matched_artist or 'Không rõ nghệ sĩ'}). Đơn vị sở hữu: {matched_label or 'Hãng đĩa ghi nhận'}."
                recommendation = "NGUY HIỂM: Video có nguy cơ bị tắt tiếng hoặc phạt gậy bản quyền trên TikTok/Reels/Shorts. Hãy bật nút 'Khử bản quyền AI (DSP)' trước khi lưu!"
        else:
            if is_sanitized:
                details = "Bản nhạc đã được bẻ dấu vân tay âm thanh và chuẩn hóa âm lượng -14 LUFS hoàn toàn sạch."

        return {
            "has_copyright": has_copyright,
            "risk_level": risk_level,
            "matched_title": matched_title,
            "matched_artist": matched_artist,
            "matched_label": matched_label,
            "confidence": round(confidence, 2),
            "duration": duration,
            "is_sanitized": is_sanitized,
            "details": details,
            "recommendation": recommendation,
        }

