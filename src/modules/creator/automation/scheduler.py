import asyncio
import logging
from typing import Optional

from src.modules.creator.automation.repository import AutomationMongoRepository
from src.modules.creator.automation.service import AutomationService

logger = logging.getLogger("automation_scheduler")


class AutomationScheduler:
    _instance: Optional["AutomationScheduler"] = None

    def __init__(self):
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.repo = AutomationMongoRepository()
        self.service = AutomationService(self.repo)

    @classmethod
    def get_instance(cls) -> "AutomationScheduler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info("AutomationScheduler background task đã khởi động thành công.")

    def stop(self) -> None:
        self.is_running = False
        if self.task and not self.task.done():
            self.task.cancel()
        logger.info("AutomationScheduler background task đã dừng.")

    async def _run_loop(self) -> None:
        """Vòng lặp định kỳ kiểm tra các chiến dịch automation đã đến hạn chạy."""
        # Nghỉ 10 giây lúc vừa khởi động để server ổn định kết nối
        await asyncio.sleep(10)

        while self.is_running:
            try:
                # Tự động giải phóng các campaign bị kẹt trạng thái 'running' quá 10 phút
                await self.repo.recover_stuck_campaigns(timeout_minutes=10)

                due_campaigns = await self.repo.get_due_campaigns()
                if due_campaigns:
                    logger.info(f"Phát hiện {len(due_campaigns)} chiến dịch Automation đến hạn chạy.")
                    for camp in due_campaigns:
                        if not self.is_running:
                            break
                        try:
                            logger.info(f"Đang tự động thực thi chiến dịch: {camp.get('name')}...")
                            await self.service.execute_campaign_cycle(camp)
                        except Exception as cycle_err:
                            logger.error(f"Lỗi khi chạy chiến dịch {camp.get('id')}: {cycle_err}")

            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                logger.error(f"Lỗi vòng lặp AutomationScheduler: {loop_err}")

            # Kiểm tra mỗi 45 giây
            await asyncio.sleep(45)

