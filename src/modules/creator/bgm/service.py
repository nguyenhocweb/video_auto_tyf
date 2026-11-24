import os
import uuid
import random
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import UploadFile
from src.core.config import settings
from src.core.engines.dubbing.audio_sanitizer import AudioSanitizerEngine
from src.core.engines.dubbing.copyright_scanner import AudioCopyrightScannerEngine
from src.modules.creator.bgm.repository import BgmMongoRepository

logger = logging.getLogger("bgm_service")


class BgmService:
    """Service nghiệp vụ quản lý kho nhạc nền, thẩm định bản quyền và bẻ sóng âm chống Content ID."""

    def __init__(self, repo: Optional[BgmMongoRepository] = None):
        self.repo = repo or BgmMongoRepository()

    async def list_tracks(
        self, user_id: Optional[str] = None, mood: Optional[str] = None, skip: int = 0, limit: int = 50
    ) -> Dict[str, Any]:
        """Lấy danh sách bài nhạc kèm danh mục mood."""
        await self.repo.seed_presets_if_needed()
        items = await self.repo.get_tracks(user_id=user_id, mood=mood, skip=skip, limit=limit)
        total = await self.repo.count_tracks(user_id=user_id, mood=mood)
        moods = ["chill", "upbeat", "funny", "asmr", "cinematic", "general"]
        return {"items": items, "total": total, "moods": moods}

    async def upload_bgm(
        self,
        file: UploadFile,
        user_id: str,
        title: Optional[str] = None,
        mood: str = "chill",
        tags_str: str = "",
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        sanitize_audio: bool = True,
    ) -> Dict[str, Any]:
        """Tải lên bản nhạc hoặc video, tự động bóc tách âm thanh sang MP3, cắt đoạn và bẻ sóng âm DSP."""
        allowed_media = [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"]
        clean_ext = Path(file.filename or "audio.mp3").suffix.lower()
        if clean_ext not in allowed_media:
            clean_ext = ".mp3"

        settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        settings.BGM_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        raw_name = f"raw_{uuid.uuid4().hex[:12]}{clean_ext}"
        raw_path = settings.TEMP_DIR / raw_name

        content = await file.read()
        with open(raw_path, "wb") as f:
            f.write(content)

        final_name = f"bgm_{uuid.uuid4().hex[:12]}.mp3"
        final_path = settings.BGM_STORAGE_DIR / final_name

        ok, dur = AudioSanitizerEngine.sanitize_and_trim(
            input_path=raw_path,
            output_path=final_path,
            start_time=start_time,
            end_time=end_time,
            sanitize=sanitize_audio,
        )

        if not ok or not final_path.exists():
            import subprocess
            fallback_cmd = ["ffmpeg", "-y", "-i", str(raw_path), "-vn", "-c:a", "libmp3lame", "-b:a", "192k", str(final_path)]
            subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            dur = AudioSanitizerEngine.probe_audio_duration(final_path)

        # Xóa file gốc (video hoặc audio thô), chỉ lưu duy nhất file âm thanh MP3
        if raw_path.exists():
            try:
                raw_path.unlink()
            except Exception:
                pass

        tags = [t.strip().lower() for t in tags_str.split(",") if t.strip()]
        track_title = title.strip() if title and title.strip() else Path(file.filename or "Nhạc Mới").stem

        data = {
            "user_id": user_id,
            "title": track_title,
            "mood": mood if mood in ["chill", "upbeat", "funny", "asmr", "cinematic", "general"] else "chill",
            "duration": dur,
            "audio_url": f"/api/v1/creator/bgm/stream/{final_path.name}",
            "file_path": str(final_path),
            "is_preset": False,
            "sanitized": sanitize_audio,
            "tags": tags,
        }
        return await self.repo.create_track(data)

    async def check_copyright_by_file(self, file: UploadFile) -> Dict[str, Any]:
        """Quét bản quyền trực tiếp từ file âm thanh hoặc video người dùng vừa chọn trước khi tải lên."""
        settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        allowed_media = [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"]
        clean_ext = Path(file.filename or "audio.mp3").suffix.lower()
        if clean_ext not in allowed_media:
            clean_ext = ".mp3"
        temp_path = settings.TEMP_DIR / f"scan_{uuid.uuid4().hex[:12]}{clean_ext}"

        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)

        try:
            return AudioCopyrightScannerEngine.scan_audio(temp_path, is_sanitized=False)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    async def check_copyright_by_track_id(self, track_id: str) -> Dict[str, Any]:
        """Quét bản quyền cho một bài nhạc đang có sẵn trong kho."""
        track = await self.repo.get_track_by_id(track_id)
        if not track:
            raise ValueError("Không tìm thấy bài nhạc này.")
        file_path_str = track.get("file_path")
        if not file_path_str or not os.path.exists(file_path_str):
            raise ValueError("File âm thanh của bài nhạc không tồn tại trên máy chủ.")

        is_sanitized = bool(track.get("sanitized", False) or track.get("is_preset", False))
        return AudioCopyrightScannerEngine.scan_audio(Path(file_path_str), is_sanitized=is_sanitized)

    async def get_random_bgm_for_auto(
        self,
        user_id: Optional[str] = None,
        mood: Optional[str] = None,
        preferred_id: Optional[str] = None,
        candidate_ids: Optional[List[str]] = None,
        min_duration: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy 1 bản nhạc thích hợp cho tác vụ Auto Re-up:
        - Nếu có candidate_ids (danh sách ID các bài được user chọn): Lấy các bài tương ứng.
        - Ưu tiên các bài có duration >= min_duration (thời lượng âm thanh lớn hơn video).
        - Random 1 bài trong nhóm thỏa mãn. Nếu không có bài nào >= min_duration thì random trong toàn bộ pool.
        """
        await self.repo.seed_presets_if_needed()
        tracks: List[Dict[str, Any]] = []

        if candidate_ids and len(candidate_ids) > 0:
            tracks = await self.repo.get_tracks_by_ids(candidate_ids)
            logger.info(f"Đã nạp {len(tracks)}/{len(candidate_ids)} bài BGM từ danh sách user chọn để random.")

        if not tracks and preferred_id:
            track = await self.repo.get_track_by_id(preferred_id)
            if track:
                return track

        if not tracks:
            tracks = await self.repo.get_tracks(user_id=user_id, mood=mood, limit=100)

        if not tracks:
            return None

        # Yêu cầu: Đoạn âm thanh phải lớn hơn video (duration >= min_duration)
        if min_duration and min_duration > 0:
            long_tracks = [t for t in tracks if float(t.get("duration", 0.0)) >= min_duration]
            if long_tracks:
                logger.info(
                    f"Có {len(long_tracks)}/{len(tracks)} bài BGM có thời lượng >= {min_duration:.1f}s, tiến hành random 1 bài."
                )
                return random.choice(long_tracks)
            logger.warning(
                f"Không có bài BGM nào trong pool dài hơn video ({min_duration:.1f}s). "
                "Hệ thống sẽ random trong pool và tự động loop âm thanh để phủ kín video."
            )

        return random.choice(tracks)

    async def get_bgm_by_id(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết một bản nhạc theo track_id."""
        return await self.repo.get_track_by_id(track_id)

    async def delete_track(self, track_id: str, user_id: str) -> bool:
        """Xóa bản nhạc khỏi CSDL và ổ đĩa nếu là file local."""
        track = await self.repo.get_track_by_id(track_id)
        if not track or track.get("is_preset"):
            return False
        f_path = track.get("file_path")
        if f_path and os.path.exists(f_path):
            try:
                os.remove(f_path)
            except Exception:
                pass
        return await self.repo.delete_track(track_id=track_id, user_id=user_id)
