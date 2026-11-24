import logging
from typing import Optional
from src.modules.shared.notifications.service import NotificationService

logger = logging.getLogger("dubbing_notifier")


class DubbingNotifier:
    _service: Optional[NotificationService] = None

    @classmethod
    def get_service(cls) -> NotificationService:
        if cls._service is None:
            cls._service = NotificationService()
        return cls._service

    @classmethod
    async def notify_completed(
        cls,
        user_id: str,
        job_id: str,
        title: Optional[str] = None,
        video_url: Optional[str] = None,
        cover_url: Optional[str] = None,
    ) -> None:
        try:
            safe_title = title or f"Video #{job_id[:6]}"
            safe_url = video_url or f"/api/v1/creator/dubbing/download/final_{job_id}.mp4"
            await cls.get_service().create_and_push(
                user_id=user_id,
                type="JOB_COMPLETED",
                title=f"Đã hoàn thành video #{job_id[:6]}",
                message=f"Video '{safe_title[:60]}' đã được dịch và xử lý hoàn tất 100%.",
                level="SUCCESS",
                target_role="CREATOR",
                metadata={"job_id": job_id, "video_url": safe_url, "cover_url": cover_url},
            )
        except Exception as e:
            logger.debug(f"Lỗi notify_completed: {e}")

    @classmethod
    async def notify_failed(
        cls,
        user_id: str,
        job_id: str,
        err_msg: str,
        title: Optional[str] = None,
    ) -> None:
        try:
            safe_title = title or f"Video #{job_id[:6]}"
            is_trans_err = any(k in err_msg.lower() for k in ["dịch", "gemini", "qwen", "quota", "translate"])
            notif_type = "JOB_TRANSLATION_FAILED" if is_trans_err else "JOB_FAILED"
            title_text = f"Lỗi dịch thuật: #{job_id[:6]}" if is_trans_err else f"Thất bại: #{job_id[:6]}"
            await cls.get_service().create_and_push(
                user_id=user_id,
                type=notif_type,
                title=title_text,
                message=f"{err_msg[:120]}. Bạn có muốn thực thi lại không?",
                level="ERROR",
                target_role="CREATOR",
                metadata={"job_id": job_id, "can_retry": True, "error_detail": err_msg, "video_title": safe_title},
            )
        except Exception as e:
            logger.debug(f"Lỗi notify_failed: {e}")
