import logging
from typing import List, Dict, Any, Optional
from src.modules.shared.notifications.repository import NotificationMongoRepository
from src.modules.shared.notifications.schemas import NotificationCreateRequest
from src.modules.shared.ws.notification_ws import notify_user

logger = logging.getLogger("notifications_service")


class NotificationService:
    def __init__(self, repo: Optional[NotificationMongoRepository] = None):
        self.repo = repo or NotificationMongoRepository()

    async def create_and_push(
        self,
        user_id: Optional[str],
        type: str,
        title: str,
        message: str,
        level: str = "INFO",
        target_role: str = "CREATOR",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Tạo thông báo trong Database và đồng thời bắn WebSocket rung chuông Realtime trên giao diện."""
        doc = await self.repo.create({
            "user_id": user_id,
            "target_role": target_role,
            "type": type,
            "title": title,
            "message": message,
            "level": level,
            "metadata": metadata or {},
        })

        # Bắn WebSocket Realtime tới Client nếu có user_id
        if user_id:
            try:
                unread = await self.repo.get_unread_count(user_id, role=target_role)
                await notify_user(
                    user_id=user_id,
                    event_type="NOTIFICATION_NEW",
                    data={
                        "notification": doc,
                        "unread_count": unread,
                    },
                )
            except Exception as ws_err:
                logger.debug(f"Không thể bắn WS notification: {ws_err}")

        return doc

    async def get_user_notifications(
        self,
        user_id: str,
        role: str = "USER",
        is_read: Optional[bool] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> Dict[str, Any]:
        items = await self.repo.get_user_notifications(user_id, role, is_read, limit, skip)
        unread = await self.repo.get_unread_count(user_id, role)
        return {
            "total": len(items),
            "unread_count": unread,
            "notifications": items,
        }

    async def get_unread_count(self, user_id: str, role: str = "USER") -> int:
        return await self.repo.get_unread_count(user_id, role)

    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        return await self.repo.mark_as_read(notification_id, user_id)

    async def mark_all_as_read(self, user_id: str) -> int:
        return await self.repo.mark_all_as_read(user_id)

    async def delete_notification(self, notification_id: str, user_id: str) -> bool:
        return await self.repo.delete(notification_id, user_id)

