import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from src.modules.shared.auth.dependencies import get_current_user
from src.modules.shared.notifications.service import NotificationService
from src.modules.shared.notifications.schemas import (
    NotificationListResponse,
    UnreadCountResponse,
)

logger = logging.getLogger("notifications_router")

notifications_router = APIRouter(prefix="/notifications", tags=["Shared Notifications"])


def get_notification_service() -> NotificationService:
    return NotificationService()


@notifications_router.get(
    "",
    response_model=NotificationListResponse,
    summary="Lấy danh sách thông báo của người dùng kèm phân trang và lọc",
)
async def get_notifications_endpoint(
    is_read: Optional[bool] = Query(None, description="Lọc theo đã đọc (True) hoặc chưa đọc (False)"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    user_id = current_user["id"]
    role = current_user.get("role", "USER")
    return await service.get_user_notifications(user_id, role=role, is_read=is_read, limit=limit, skip=skip)


@notifications_router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Lấy số lượng thông báo chưa đọc để hiển thị badge chuông đỏ",
)
async def get_unread_count_endpoint(
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    user_id = current_user["id"]
    role = current_user.get("role", "USER")
    count = await service.get_unread_count(user_id, role=role)
    return {"unread_count": count}


@notifications_router.patch(
    "/{notification_id}/read",
    summary="Đánh dấu một thông báo là đã đọc",
)
async def mark_as_read_endpoint(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    success = await service.mark_as_read(notification_id, current_user["id"])
    return {"success": success}


@notifications_router.post(
    "/mark-all-read",
    summary="Đánh dấu tất cả thông báo là đã đọc",
)
async def mark_all_as_read_endpoint(
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    count = await service.mark_all_as_read(current_user["id"])
    return {"success": True, "marked_count": count}


@notifications_router.delete(
    "/{notification_id}",
    summary="Xóa một thông báo",
)
async def delete_notification_endpoint(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    success = await service.delete_notification(notification_id, current_user["id"])
    return {"success": success}

