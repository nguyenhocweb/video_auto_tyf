from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class PublishedDestination(BaseModel):
    platform: str  # "facebook" | "youtube" | "tiktok"
    target_name: str
    target_id: Optional[str] = None
    post_url: Optional[str] = None
    status: str = "success"  # "success" | "failed"
    published_at: Optional[str] = None


class NotificationMetadata(BaseModel):
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    channel_name: Optional[str] = None
    channel_url: Optional[str] = None
    channel_avatar: Optional[str] = None
    video_item_id: Optional[str] = None
    video_url: Optional[str] = None
    video_title: Optional[str] = None
    translated_title: Optional[str] = None
    cover_url: Optional[str] = None
    current_step: Optional[str] = None
    progress_percent: Optional[int] = None
    published_destinations: Optional[List[Dict[str, Any]]] = None
    error_detail: Optional[str] = None
    job_id: Optional[str] = None
    can_retry: Optional[bool] = None


class NotificationResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    target_role: str = "CREATOR"
    type: str
    title: str
    message: str
    level: str = "INFO"
    metadata: Optional[Dict[str, Any]] = None
    is_read: bool = False
    read_at: Optional[str] = None
    created_at: str


class NotificationListResponse(BaseModel):
    total: int
    unread_count: int
    notifications: List[NotificationResponse]


class UnreadCountResponse(BaseModel):
    unread_count: int


class NotificationCreateRequest(BaseModel):
    user_id: Optional[str] = None
    target_role: str = "CREATOR"
    type: str
    title: str
    message: str
    level: str = "INFO"
    metadata: Optional[Dict[str, Any]] = None

