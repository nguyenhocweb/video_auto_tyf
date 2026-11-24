import asyncio
import logging
from typing import Dict, Any, Optional

from src.modules.shared.settings.system_settings_repository import SystemSettingsMongoRepository
from src.modules.creator.dubbing.repository import DubbingMongoRepository
from src.modules.creator.dubbing.dubbing_worker import execute_dubbing_worker

logger = logging.getLogger("dubbing_queue_manager")


class DubbingQueueManager:
    """Bộ điều phối hàng đợi xử lý Vietsub & Dubbing ngầm tuân theo cấu hình Admin."""

    _instance: Optional["DubbingQueueManager"] = None

    def __init__(self):
        self.max_concurrency = 2
        self.semaphore = asyncio.Semaphore(2)
        self.active_jobs: int = 0
        self.queued_jobs: int = 0
        self.repo = DubbingMongoRepository()
        self.settings_repo = SystemSettingsMongoRepository()

    @classmethod
    def get_instance(cls) -> "DubbingQueueManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def init_concurrency_from_db(self):
        """Khởi tạo giới hạn song song từ Database và tự động dọn dẹp các tác vụ mồ côi."""
        try:
            cfg = await self.settings_repo.get_concurrency_settings()
            self.max_concurrency = cfg.get("max_concurrency", 2)
            self.semaphore = asyncio.Semaphore(self.max_concurrency)
            logger.info(f"Initialized DubbingQueueManager with max_concurrency={self.max_concurrency}")
        except Exception as exc:
            logger.warning(f"Could not load concurrency from DB for DubbingQueue: {exc}")

        # Tự động dọn dẹp các tác vụ bị chết khi server reload/restart
        try:
            await self.repo.cleanup_stale_processing_jobs()
        except Exception as cln_exc:
            logger.warning(f"Error cleaning stale dubbing jobs: {cln_exc}")

    def update_max_concurrency(self, new_limit: int):
        """Cập nhật tức thì số luồng chạy song song khi Admin thay đổi."""
        self.max_concurrency = max(1, min(new_limit, 64))
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        logger.info(f"DubbingQueueManager max_concurrency updated to {self.max_concurrency}")

    def get_queue_status(self) -> Dict[str, Any]:
        return {
            "max_concurrency": self.max_concurrency,
            "active_jobs": self.active_jobs,
            "queued_jobs": self.queued_jobs,
        }

    async def enqueue_auto_dubbing_task(
        self,
        job_id: str,
        user_id: str,
        payload_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Đưa tác vụ Vietsub & Thuyết Minh tự động vào hàng đợi chạy ngầm."""
        self.queued_jobs += 1
        asyncio.create_task(self._run_task_with_semaphore(job_id, user_id, payload_data))
        return {
            "job_id": job_id,
            "status": "pending",
            "progress_step": "Đang chờ vào hàng đợi...",
            "message": "Đã tiếp nhận vào hàng đợi xử lý ngầm.",
        }

    async def retry_job(self, job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Thử lại một tác vụ thất bại hoặc bị gián đoạn."""
        job = await self.repo.get_job_by_id(job_id, user_id)
        if not job:
            return None

        # Reset tiến trình về pending
        await self.repo.update_progress(
            job_id=job_id,
            status="pending",
            progress_step="Đang chuẩn bị thử lại...",
            progress_percent=0,
            error_message=None,
        )

        payload_data = {
            "url": job.get("source_url") or job.get("video_url"),
            "mode": job.get("mode", "both"),
            "voice_source": job.get("voice_source", "preset"),
            "voice_preset": job.get("voice_preset", "vi-VN-NamMinhNeural"),
            "voice_profile_id": job.get("voice_profile_id"),
            "remove_subtitles": job.get("remove_subtitles", True),
            "bgm_volume": job.get("bgm_volume", 0.18),
            "voice_volume": job.get("voice_volume", 1.0),
        }
        await self.enqueue_auto_dubbing_task(job_id, user_id, payload_data)
        return await self.repo.get_job_by_id(job_id, user_id)

    async def _run_task_with_semaphore(
        self, job_id: str, user_id: str, payload_data: Dict[str, Any]
    ):
        """Bọc thực thi worker bên trong Semaphore giới hạn song song."""
        async with self.semaphore:
            self.queued_jobs = max(0, self.queued_jobs - 1)
            self.active_jobs += 1
            logger.info(f"Bắt đầu chạy ngầm Dubbing Job: {job_id} (Active: {self.active_jobs})")
            try:
                await execute_dubbing_worker(job_id, user_id, payload_data, self.repo)
            finally:
                self.active_jobs = max(0, self.active_jobs - 1)
