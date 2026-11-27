import os
import uuid
import shutil
import random
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from fastapi import UploadFile
from src.core.config import settings
from src.core.engines.dubbing.audio_sanitizer import AudioSanitizerEngine
from src.core.engines.dubbing.copyright_scanner import AudioCopyrightScannerEngine
from src.modules.creator.bgm.repository import BgmMongoRepository
from src.modules.creator.bgm.storage_helper import BgmStorageHelper
from src.modules.shared.cloudinary.service import FastCloudinaryService

logger = logging.getLogger("bgm_service")

VALID_MOODS = ["chill", "upbeat", "funny", "asmr", "cinematic", "general"]
ALLOWED_MEDIA_EXTS = [
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
    ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v",
]


class BgmService:
    """Service nghiệp vụ quản lý kho nhạc nền (lưu Cloudinary CDN), thẩm định bản quyền và bẻ sóng âm DSP."""

    def __init__(self, repo: Optional[BgmMongoRepository] = None):
        self.repo = repo or BgmMongoRepository()

    async def list_tracks(
        self, user_id: Optional[str] = None, mood: Optional[str] = None, skip: int = 0, limit: int = 50
    ) -> Dict[str, Any]:
        """Lấy danh sách bài nhạc kèm danh mục mood."""
        await self.repo.seed_presets_if_needed()
        items = await self.repo.get_tracks(user_id=user_id, mood=mood, skip=skip, limit=limit)
        total = await self.repo.count_tracks(user_id=user_id, mood=mood)
        return {"items": items, "total": total, "moods": VALID_MOODS}

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
        """Tải lên nhạc/video -> tách & khử bản quyền DSP sang MP3 -> đẩy thẳng lên Cloudinary CDN."""
        clean_ext = Path(file.filename or "audio.mp3").suffix.lower()
        if clean_ext not in ALLOWED_MEDIA_EXTS:
            clean_ext = ".mp3"

        settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        settings.BGM_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        raw_path = settings.TEMP_DIR / f"raw_{uuid.uuid4().hex[:12]}{clean_ext}"
        final_name = f"bgm_{uuid.uuid4().hex[:12]}.mp3"
        temp_mp3_path = settings.TEMP_DIR / final_name

        content = await file.read()
        with open(raw_path, "wb") as f:
            f.write(content)

        try:
            ok, dur = AudioSanitizerEngine.sanitize_and_trim(
                input_path=raw_path,
                output_path=temp_mp3_path,
                start_time=start_time,
                end_time=end_time,
                sanitize=sanitize_audio,
            )

            if not ok or not temp_mp3_path.exists():
                fallback_cmd = [
                    "ffmpeg", "-y", "-i", str(raw_path),
                    "-vn", "-c:a", "libmp3lame", "-b:a", "192k", str(temp_mp3_path),
                ]
                subprocess.run(fallback_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
                dur = AudioSanitizerEngine.probe_audio_duration(temp_mp3_path)

            # Đẩy file MP3 đã làm sạch lên Cloudinary CDN để đồng bộ mọi server (Local + VPS + Vercel)
            audio_url = f"/api/v1/creator/bgm/stream/{final_name}"
            cloudinary_public_id: Optional[str] = None
            stored_file_path: Optional[str] = None

            cloud_res = await FastCloudinaryService.upload_large_file(
                file_path=str(temp_mp3_path),
                filename=final_name,
                folder="video_ai/bgm",
                resource_type="video",
            )
            if cloud_res and cloud_res.get("secure_url"):
                audio_url = str(cloud_res["secure_url"])
                cloudinary_public_id = cloud_res.get("public_id")
                logger.info(f"Đã tải nhạc BGM '{final_name}' lên Cloudinary: {audio_url}")
            else:
                # Dự phòng lưu local chỉ khi Cloudinary tạm lỗi mạng
                local_fallback = settings.BGM_STORAGE_DIR / final_name
                shutil.copy2(str(temp_mp3_path), str(local_fallback))
                stored_file_path = str(local_fallback)
                logger.warning(f"Cloudinary không khả dụng, tạm lưu BGM cục bộ: {local_fallback}")
        finally:
            for p in (raw_path, temp_mp3_path):
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass

        tags = [t.strip().lower() for t in tags_str.split(",") if t.strip()]
        track_title = title.strip() if title and title.strip() else Path(file.filename or "Nhạc Mới").stem

        data = {
            "user_id": user_id,
            "title": track_title,
            "mood": mood if mood in VALID_MOODS else "chill",
            "duration": dur,
            "audio_url": audio_url,
            "cloudinary_public_id": cloudinary_public_id,
            "file_path": stored_file_path,
            "is_preset": False,
            "sanitized": sanitize_audio,
            "tags": tags,
        }
        return await self.repo.create_track(data)

    async def check_copyright_by_file(self, file: UploadFile) -> Dict[str, Any]:
        """Quét bản quyền trực tiếp từ file âm thanh hoặc video người dùng vừa chọn trước khi tải lên."""
        settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        clean_ext = Path(file.filename or "audio.mp3").suffix.lower()
        if clean_ext not in ALLOWED_MEDIA_EXTS:
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
        """Quét bản quyền cho một bài nhạc đang có sẵn trong kho (tự tải từ Cloudinary về nếu cần)."""
        track = await self.repo.get_track_by_id(track_id)
        if not track:
            raise ValueError("Không tìm thấy bài nhạc này.")

        local_path = await self.resolve_track_to_local_file(track, use_cache=True)
        if not local_path or not os.path.exists(local_path):
            raise ValueError("File âm thanh của bài nhạc không tồn tại trên máy chủ hoặc Cloudinary.")

        is_sanitized = bool(track.get("sanitized", False) or track.get("is_preset", False))
        return AudioCopyrightScannerEngine.scan_audio(Path(local_path), is_sanitized=is_sanitized)

    async def resolve_track_to_local_file(
        self, track: Optional[Dict[str, Any]], use_cache: bool = True
    ) -> Optional[str]:
        """Đảm bảo bản nhạc BGM có file MP3 hợp lệ trên đĩa cục bộ (tự tải từ Cloudinary nếu cần)."""
        return await BgmStorageHelper.resolve_track_to_local_file(track, use_cache=use_cache)

    async def _collect_candidate_tracks(
        self,
        user_id: Optional[str] = None,
        mood: Optional[str] = None,
        preferred_id: Optional[str] = None,
        candidate_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Tập hợp danh sách các bài BGM ứng viên theo độ ưu tiên."""
        await self.repo.seed_presets_if_needed()
        tracks: List[Dict[str, Any]] = []

        if candidate_ids:
            tracks = await self.repo.get_tracks_by_ids(candidate_ids)
            logger.info(f"Đã nạp {len(tracks)}/{len(candidate_ids)} bài BGM từ danh sách user chọn.")

        if not tracks and preferred_id:
            preferred = await self.repo.get_track_by_id(preferred_id)
            if preferred:
                tracks = [preferred]

        if not tracks:
            tracks = await self.repo.get_tracks(user_id=user_id, mood=mood, limit=100)

        return tracks

    async def get_random_bgm_for_auto(
        self,
        user_id: Optional[str] = None,
        mood: Optional[str] = None,
        preferred_id: Optional[str] = None,
        candidate_ids: Optional[List[str]] = None,
        min_duration: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Lấy 1 bản nhạc thích hợp cho tác vụ Auto Re-up, ưu tiên duration >= min_duration."""
        tracks = await self._collect_candidate_tracks(user_id, mood, preferred_id, candidate_ids)
        if not tracks:
            return None

        if min_duration and min_duration > 0:
            long_tracks = [t for t in tracks if float(t.get("duration", 0.0)) >= min_duration]
            if long_tracks:
                return random.choice(long_tracks)
        return random.choice(tracks)

    async def pick_and_resolve_random_bgm(
        self,
        user_id: Optional[str] = None,
        mood: Optional[str] = None,
        preferred_id: Optional[str] = None,
        candidate_ids: Optional[List[str]] = None,
        min_duration: Optional[float] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Chọn ngẫu nhiên bài BGM và đảm bảo tải về file cục bộ sẵn sàng cho FFmpeg.
        Nếu bài đầu tiên bị thiếu file/lỗi mạng -> tự động chuyển sang bài hợp lệ tiếp theo trong pool.
        """
        tracks = await self._collect_candidate_tracks(user_id, mood, preferred_id, candidate_ids)
        if not tracks:
            return None, None

        if min_duration and min_duration > 0:
            long_tracks = [t for t in tracks if float(t.get("duration", 0.0)) >= min_duration]
            short_tracks = [t for t in tracks if float(t.get("duration", 0.0)) < min_duration]
            random.shuffle(long_tracks)
            random.shuffle(short_tracks)
            ordered_pool = long_tracks + short_tracks
        else:
            ordered_pool = list(tracks)
            random.shuffle(ordered_pool)

        for track in ordered_pool:
            local_path = await self.resolve_track_to_local_file(track, use_cache=True)
            if local_path:
                logger.info(
                    f"Đã chọn & sẵn sàng BGM '{track.get('title')}' "
                    f"(duration={track.get('duration')}s) -> {local_path}"
                )
                return track, local_path

        # Fallback cuối: nếu toàn bộ danh sách user chọn bị hỏng -> lấy preset hệ thống
        if candidate_ids:
            logger.warning("Các bài BGM được chọn đều không có file khả dụng, chuyển sang nhạc preset sạch...")
            preset_tracks = await self.repo.get_tracks(user_id=None, mood=mood, limit=20)
            random.shuffle(preset_tracks)
            for track in preset_tracks:
                local_path = await self.resolve_track_to_local_file(track, use_cache=True)
                if local_path:
                    return track, local_path

        return None, None

    async def get_bgm_by_id(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết một bản nhạc theo track_id."""
        return await self.repo.get_track_by_id(track_id)

    async def get_track_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """Tìm bài nhạc theo tên file gốc (hỗ trợ redirect link stream cũ)."""
        return await self.repo.get_track_by_filename(filename)

    async def delete_track(self, track_id: str, user_id: str) -> bool:
        """Xóa bản nhạc khỏi Cloudinary CDN, ổ đĩa cache cục bộ và CSDL."""
        track = await self.repo.get_track_by_id(track_id)
        if not track or track.get("is_preset"):
            return False

        public_id = track.get("cloudinary_public_id")
        if public_id:
            try:
                await FastCloudinaryService.delete_asset(public_id, resource_type="video")
            except Exception as ex:
                logger.warning(f"Không thể xóa BGM trên Cloudinary ({public_id}): {ex}")

        BgmStorageHelper.cleanup_local_files(track)
        return await self.repo.delete_track(track_id=track_id, user_id=user_id)
