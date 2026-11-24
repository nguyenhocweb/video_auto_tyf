import time
import asyncio
import logging
from typing import Dict, Any, Optional
from src.core.config import settings
from src.modules.shared.voice.audio_generation_repository import AudioGenerationMongoRepository
from src.modules.shared.settings.system_settings_repository import SystemSettingsMongoRepository
from src.modules.shared.voice.service import OmniVoiceService
from src.modules.shared.voice.schemas import VoiceSynthesizeFromProfileRequest
from src.modules.shared.ws.notification_ws import notify_user

logger = logging.getLogger("voice_queue_manager")


class VoiceGenerationQueueManager:
    """Bộ điều phối hàng đợi sinh giọng nói ngầm & kiểm soát mức tải song song."""

    _instance: Optional["VoiceGenerationQueueManager"] = None

    def __init__(self):
        self.semaphore = asyncio.Semaphore(2)  # Mặc định 2 luồng song song
        self.max_concurrency = 2
        self.active_jobs: int = 0
        self.queued_jobs: int = 0
        self.repo = AudioGenerationMongoRepository()
        self.settings_repo = SystemSettingsMongoRepository()

    @classmethod
    def get_instance(cls) -> "VoiceGenerationQueueManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def init_concurrency_from_db(self):
        """Khởi tạo giới hạn song song từ cấu hình Admin lưu trong Database."""
        try:
            cfg = await self.settings_repo.get_concurrency_settings()
            self.max_concurrency = cfg.get("max_concurrency", 2)
            self.semaphore = asyncio.Semaphore(self.max_concurrency)
            logger.info(f"Initialized QueueManager with max_concurrency={self.max_concurrency}")
        except Exception as exc:
            logger.warning(f"Could not load concurrency from DB: {exc}")

    def update_max_concurrency(self, new_limit: int):
        """Cập nhật tức thì số luồng chạy song song từ màn hình Admin."""
        self.max_concurrency = max(1, min(new_limit, 64))
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        logger.info(f"QueueManager max_concurrency updated to {self.max_concurrency}")

    def get_queue_status(self) -> Dict[str, Any]:
        """Lấy thông số tải hàng đợi hiện tại."""
        return {
            "max_concurrency": self.max_concurrency,
            "active_jobs": self.active_jobs,
            "queued_jobs": self.queued_jobs,
        }

    async def enqueue_synthesize_task(
        self,
        generation_id: str,
        user_id: str,
        payload_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Đưa tác vụ sinh giọng nói vào hàng đợi xử lý ngầm."""
        self.queued_jobs += 1
        queue_pos = self.queued_jobs

        # Khởi chạy coroutine ngầm độc lập
        asyncio.create_task(
            self._execute_worker_task(generation_id, user_id, payload_data)
        )

        return {
            "generation_id": generation_id,
            "status": "PENDING",
            "queue_position": queue_pos,
            "message": "Yêu cầu đã được tiếp nhận vào hàng đợi xử lý ngầm",
        }

    async def _execute_worker_task(
        self,
        generation_id: str,
        user_id: str,
        payload_data: Dict[str, Any],
    ):
        """Tiến trình worker chạy ngầm: Chờ Semaphore, gọi AI, lưu DB và bắn WebSocket."""
        # Chờ lượt khi các luồng song song đạt ngưỡng giới hạn
        async with self.semaphore:
            self.queued_jobs = max(0, self.queued_jobs - 1)
            self.active_jobs += 1
            start_time = time.time()

            # 1. Cập nhật trạng thái PROCESSING trong DB
            await self.repo.update_generation(generation_id, {
                "status": "PROCESSING",
            })

            # Thông báo realtime tới user là task bắt đầu được xử lý
            await notify_user(user_id, "AUDIO_GENERATION_PROCESSING", {
                "id": generation_id,
                "status": "PROCESSING",
                "message": "AI đang tiến hành tổng hợp giọng đọc...",
            })

            try:
                # 2. Thực thi tổng hợp giọng nói qua OmniVoiceService
                service = OmniVoiceService()
                req = VoiceSynthesizeFromProfileRequest(
                    profile_id_or_path=payload_data["profile_id_or_path"],
                    text=payload_data["text"],
                    speed=payload_data.get("speed", 1.0),
                    num_step=payload_data.get("num_step", settings.OMNIVOICE_DEFAULT_STEPS),
                )
                res = await service.synthesize_from_profile(req)
                elapsed = round(time.time() - start_time, 2)

                cloud_audio = {
                    "public_id": res.audio_filename,
                    "secure_url": res.cloudinary_url or res.audio_path,
                    "mp3_stream_url": res.mp3_stream_url,
                    "duration_seconds": res.duration_seconds,
                    "sample_rate": res.sample_rate,
                    "format": "wav",
                    "bytes": 0,
                }

                # 3. Cập nhật COMPLETED trong Database
                await self.repo.update_generation(generation_id, {
                    "status": "COMPLETED",
                    "cloudinary_audio": cloud_audio,
                    "process_time_seconds": elapsed,
                })

                # 4. Bắn thông báo Realtime WebSocket
                await notify_user(user_id, "AUDIO_GENERATION_COMPLETED", {
                    "id": generation_id,
                    "status": "COMPLETED",
                    "input_text": payload_data["text"],
                    "voice_name": payload_data.get("voice_name", "Giọng AI"),
                    "audio_url": res.cloudinary_url or res.audio_path,
                    "duration_seconds": res.duration_seconds,
                    "process_time_seconds": elapsed,
                    "message": "🎉 Bản thuyết minh video của bạn đã tạo xong!",
                })

            except Exception as exc:
                logger.error(f"Error in synthesize worker: {exc}")
                await self.repo.update_generation(generation_id, {
                    "status": "FAILED",
                    "error_message": str(exc),
                })
                await notify_user(user_id, "AUDIO_GENERATION_FAILED", {
                    "id": generation_id,
                    "status": "FAILED",
                    "error_message": str(exc),
                    "message": f"Không thể tạo âm thanh: {str(exc)}",
                })
            finally:
                self.active_jobs = max(0, self.active_jobs - 1)

