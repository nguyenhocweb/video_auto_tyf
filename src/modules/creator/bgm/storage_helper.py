import os
import uuid
import shutil
import asyncio
import logging
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional

from src.core.config import settings
from src.core.engines.dubbing.bgm_synthesizer import ensure_preset_audio_files

logger = logging.getLogger("bgm_storage_helper")

MIN_VALID_AUDIO_BYTES = 1024


class BgmStorageHelper:
    """Helper tải và quản lý cache cục bộ cho các file BGM lưu trên Cloudinary CDN."""

    @staticmethod
    def _download_audio_sync(url: str, target_path: Path) -> bool:
        """Tải file audio từ URL (Cloudinary CDN) về đường dẫn đích với ghi atomic tránh lỗi file hỏng."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = target_path.with_name(f"{target_path.name}.{uuid.uuid4().hex[:6]}.part")
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }

        for attempt in range(2):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=45) as resp, open(part_path, "wb") as out:
                    shutil.copyfileobj(resp, out)

                if part_path.exists() and part_path.stat().st_size >= MIN_VALID_AUDIO_BYTES:
                    os.replace(str(part_path), str(target_path))
                    return True
            except Exception as ex:
                logger.warning(f"Tải BGM từ CDN thất bại (lần {attempt + 1}): {url} | {ex}")
            finally:
                if part_path.exists():
                    try:
                        part_path.unlink()
                    except Exception:
                        pass
        return False

    @classmethod
    def get_cache_path(cls, track_id: str) -> Path:
        """Trả về đường dẫn cache chuẩn trên đĩa cho một track_id."""
        safe_id = "".join(c for c in str(track_id) if c.isalnum() or c in ("-", "_")) or "track"
        return settings.BGM_STORAGE_DIR / f"cache_{safe_id}.mp3"

    @classmethod
    async def resolve_track_to_local_file(
        cls,
        track: Optional[Dict[str, Any]],
        use_cache: bool = True,
    ) -> Optional[str]:
        """
        Đảm bảo bài nhạc BGM có file MP3 hợp lệ trên ổ đĩa hiện tại để FFmpeg ghép nối:
        1. Kiểm tra file_path cục bộ nếu tồn tại.
        2. Kiểm tra file trong BGM_STORAGE_DIR (tên gốc hoặc file cache theo track_id).
        3. Nếu audio_url là link HTTP(S) (Cloudinary) -> tải về cache cục bộ non-blocking.
        4. Nếu là preset hệ thống -> tự động tổng hợp lại file preset nếu thiếu.
        """
        if not track:
            return None

        track_id = str(track.get("id") or track.get("_id") or uuid.uuid4().hex[:8])
        file_path = track.get("file_path")
        audio_url = str(track.get("audio_url") or "").strip()

        # 1. File local theo đường dẫn lưu trong DB
        if file_path and isinstance(file_path, str):
            p = Path(file_path)
            if p.exists() and p.stat().st_size >= MIN_VALID_AUDIO_BYTES:
                return str(p)

            # Kiểm tra tên file trong BGM_STORAGE_DIR (trường hợp khác OS Windows/Linux)
            alt_name = Path(file_path.replace("\\", "/")).name
            if alt_name:
                cand = settings.BGM_STORAGE_DIR / alt_name
                if cand.exists() and cand.stat().st_size >= MIN_VALID_AUDIO_BYTES:
                    return str(cand)

        # 2. Kiểm tra cache cục bộ theo track_id
        cache_path = cls.get_cache_path(track_id)
        if use_cache and cache_path.exists() and cache_path.stat().st_size >= MIN_VALID_AUDIO_BYTES:
            return str(cache_path)

        # Kiểm tra tên file từ stream URL cục bộ nếu có
        if audio_url and not audio_url.startswith(("http://", "https://")):
            stream_name = Path(audio_url.split("?")[0]).name
            if stream_name:
                cand_stream = settings.BGM_STORAGE_DIR / stream_name
                if cand_stream.exists() and cand_stream.stat().st_size >= MIN_VALID_AUDIO_BYTES:
                    return str(cand_stream)

        # 3. Tải từ Cloudinary CDN hoặc URL ngoại vi
        if audio_url.startswith(("http://", "https://")):
            target_path = (
                cache_path
                if use_cache
                else (settings.TEMP_DIR / "bgm_downloads" / f"bgm_{track_id}_{uuid.uuid4().hex[:6]}.mp3")
            )
            ok = await asyncio.to_thread(cls._download_audio_sync, audio_url, target_path)
            if ok and target_path.exists():
                logger.info(f"Đã tải BGM '{track.get('title')}' từ Cloudinary về cache: {target_path.name}")
                return str(target_path)

        # 4. Fallback cho nhạc Preset hệ thống
        if track.get("is_preset"):
            mood = str(track.get("mood") or "chill").lower()
            await asyncio.to_thread(ensure_preset_audio_files, settings.BGM_STORAGE_DIR)
            preset_path = settings.BGM_STORAGE_DIR / f"preset_{mood}.mp3"
            if preset_path.exists() and preset_path.stat().st_size >= MIN_VALID_AUDIO_BYTES:
                return str(preset_path)

        logger.warning(
            f"Không thể tìm hoặc tải file BGM '{track.get('title')}' "
            f"(id={track_id}, url={audio_url}, file_path={file_path})"
        )
        return None

    @classmethod
    def cleanup_local_files(cls, track: Dict[str, Any]) -> None:
        """Dọn file local gốc và file cache của bài nhạc khi người dùng xóa."""
        track_id = str(track.get("id") or track.get("_id") or "")
        candidates = []

        f_path = track.get("file_path")
        if f_path and isinstance(f_path, str):
            candidates.append(Path(f_path))
            alt_name = Path(f_path.replace("\\", "/")).name
            if alt_name:
                candidates.append(settings.BGM_STORAGE_DIR / alt_name)

        if track_id:
            candidates.append(cls.get_cache_path(track_id))

        for path in candidates:
            if path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass
