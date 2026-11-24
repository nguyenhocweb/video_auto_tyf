import io
import asyncio
import logging
from typing import Dict, Any, Optional
import cloudinary
import cloudinary.uploader
import cloudinary.utils
from src.core.config import settings

logger = logging.getLogger("cloudinary_service")

class FastCloudinaryService:
    """
    Quy trình lưu trữ Cloudinary siêu tốc (High-Speed Cloudinary Pipeline):
    1. Direct In-Memory Streaming: Stream trực tiếp từ RAM (BytesIO), không ghi file tạm ra đĩa cứng.
    2. Non-blocking Async Execution: Thực thi I/O trên worker thread riêng bằng asyncio.to_thread.
    3. Dynamic URL Generation: Tự sinh URL nén MP3 tối ưu (f_mp3,br_128k) theo thuật toán CDN tức thì.
    4. Raw Asset Support: Hỗ trợ upload trực tiếp file vector nhúng PyTorch (.pt).
    """

    _is_configured = False
    _is_active = False

    @classmethod
    def _ensure_configured(cls):
        if not cls._is_configured:
            try:
                has_cloud_name = (
                    settings.CLOUDINARY_CLOUD_NAME
                    and settings.CLOUDINARY_CLOUD_NAME != "your_cloud_name"
                    and settings.CLOUDINARY_API_KEY
                    and settings.CLOUDINARY_API_KEY != "your_api_key"
                )
                has_cloud_url = (
                    settings.CLOUDINARY_URL
                    and "your_api_key" not in settings.CLOUDINARY_URL
                    and "your_cloud_name" not in settings.CLOUDINARY_URL
                )

                if has_cloud_name:
                    cloudinary.config(
                        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
                        api_key=settings.CLOUDINARY_API_KEY,
                        api_secret=settings.CLOUDINARY_API_SECRET,
                        secure=True,
                    )
                    cls._is_active = True
                elif has_cloud_url:
                    cloudinary.config(cloudinary_url=settings.CLOUDINARY_URL)
                    cls._is_active = True
                else:
                    cls._is_active = False
            except Exception as e:
                logger.warning(f"Cloudinary configuration skipped: {e}")
                cls._is_active = False
            finally:
                cls._is_configured = True

    @classmethod
    async def upload_audio_bytes(
        cls,
        audio_bytes: bytes,
        filename: str,
        folder: str = "video_ai/voice_samples",
    ) -> Optional[Dict[str, Any]]:
        """
        Upload âm thanh trực tiếp từ bộ nhớ RAM lên Cloudinary với tốc độ tối đa.
        Nếu Cloudinary chưa được cấu hình hoặc lỗi mạng, trả về None để dùng URL cục bộ.
        """
        cls._ensure_configured()
        if not cls._is_active:
            return None

        def _sync_upload():
            buffer = io.BytesIO(audio_bytes)
            return cloudinary.uploader.upload(
                buffer,
                resource_type="video",
                folder=folder,
                public_id=filename.rsplit(".", 1)[0],
                overwrite=True,
                format="wav",
            )

        try:
            res = await asyncio.to_thread(_sync_upload)
            secure_url = res.get("secure_url", "")
            mp3_stream_url = (
                secure_url.replace("/upload/", "/upload/f_mp3,br_128k/")
                if secure_url
                else None
            )

            return {
                "public_id": res.get("public_id"),
                "secure_url": secure_url,
                "mp3_stream_url": mp3_stream_url,
                "format": res.get("format", "wav"),
                "bytes": res.get("bytes", len(audio_bytes)),
                "duration_seconds": res.get("duration", 0.0),
            }
        except Exception as exc:
            logger.warning(f"FastCloudinaryService upload_audio_bytes error: {exc}")
            return None

    @classmethod
    async def upload_raw_embedding(
        cls,
        embedding_bytes: bytes,
        profile_id: str,
        folder: str = "video_ai/voice_profiles",
    ) -> Optional[Dict[str, Any]]:
        """
        Upload file vector PyTorch (.pt) dạng Raw Asset lên Cloudinary.
        """
        cls._ensure_configured()
        if not cls._is_active:
            return None

        def _sync_upload():
            buffer = io.BytesIO(embedding_bytes)
            return cloudinary.uploader.upload(
                buffer,
                resource_type="raw",
                folder=folder,
                public_id=f"embedding_{profile_id}.pt",
                overwrite=True,
            )

        try:
            res = await asyncio.to_thread(_sync_upload)
            return {
                "public_id": res.get("public_id"),
                "secure_url": res.get("secure_url"),
                "resource_type": "raw",
                "format": "pt",
                "bytes": res.get("bytes", len(embedding_bytes)),
            }
        except Exception as exc:
            logger.warning(f"FastCloudinaryService upload_raw_embedding error: {exc}")
            return None

    @classmethod
    async def upload_large_file(
        cls,
        file_path: str,
        filename: str,
        folder: str = "video_ai/long_audio_datasets",
        resource_type: str = "video",
    ) -> Optional[Dict[str, Any]]:
        """
        Upload file dung lượng lớn (15-30 phút, lên tới 100MB+) theo phương thức chunking.
        """
        cls._ensure_configured()
        if not cls._is_active:
            return None

        def _sync_upload():
            return cloudinary.uploader.upload_large(
                file_path,
                resource_type=resource_type,
                folder=folder,
                public_id=filename.rsplit(".", 1)[0],
                chunk_size=6000000,
            )

        try:
            res = await asyncio.to_thread(_sync_upload)
            return {
                "public_id": res.get("public_id"),
                "secure_url": res.get("secure_url"),
                "format": res.get("format"),
                "bytes": res.get("bytes", 0),
                "duration_seconds": res.get("duration", 0.0),
            }
        except Exception as exc:
            logger.warning(f"FastCloudinaryService upload_large_file error: {exc}")
            return None

    @classmethod
    async def upload_video_from_url(
        cls,
        video_url: str,
        public_id: str,
        folder: str = "video_ai/downloaded_videos",
    ) -> Optional[Dict[str, Any]]:
        """Upload video trực tiếp từ remote URL lên Cloudinary."""
        cls._ensure_configured()
        if not cls._is_active:
            return None

        def _sync_upload():
            return cloudinary.uploader.upload(
                video_url,
                resource_type="video",
                folder=folder,
                public_id=public_id,
                overwrite=True,
            )

        try:
            res = await asyncio.to_thread(_sync_upload)
            return {
                "public_id": res.get("public_id"),
                "secure_url": res.get("secure_url"),
                "format": res.get("format"),
                "bytes": res.get("bytes", 0),
                "duration_seconds": res.get("duration", 0.0),
            }
        except Exception as exc:
            logger.warning(f"FastCloudinaryService upload_video_from_url error: {exc}")
            return None

    @classmethod
    async def delete_asset(cls, public_id: str, resource_type: str = "video") -> bool:
        """Xóa tài nguyên trên Cloudinary khi người dùng xóa hồ sơ/âm thanh."""
        cls._ensure_configured()

        def _sync_delete():
            res = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
            return res.get("result") == "ok"

        return await asyncio.to_thread(_sync_delete)
