import logging
from typing import List, Dict, Any, Optional
from src.modules.shared.notifications.service import NotificationService

logger = logging.getLogger("automation_notifier")


class AutomationNotifier:
    """Helper phát thông báo chi tiết từng giai đoạn cào và xuất bản video cho chiến dịch tự động."""

    _service: Optional[NotificationService] = None

    @classmethod
    def get_service(cls) -> NotificationService:
        if cls._service is None:
            cls._service = NotificationService()
        return cls._service

    @classmethod
    async def notify_crawl_started(
        cls, user_id: str, campaign_id: str, campaign_name: str, ch_name: str, ch_url: str
    ):
        try:
            await cls.get_service().create_and_push(
                user_id=user_id,
                type="AUTO_CRAWL_STARTED",
                title=f"Đang quét kênh: {ch_name}",
                message=f"Hệ thống đang kiểm tra video mới hôm nay từ kênh Douyin '{ch_name}'.",
                level="INFO",
                target_role="CREATOR",
                metadata={
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "channel_name": ch_name,
                    "channel_url": ch_url,
                    "current_step": "Quét kênh nguồn",
                },
            )
        except Exception as e:
            logger.debug(f"Lỗi notify_crawl_started: {e}")

    @classmethod
    async def notify_video_discovered(
        cls,
        user_id: str,
        campaign_id: str,
        campaign_name: str,
        ch_name: str,
        ch_url: str,
        item_id: str,
        video_url: str,
        title: str,
        cover_url: Optional[str] = None,
    ):
        try:
            await cls.get_service().create_and_push(
                user_id=user_id,
                type="AUTO_VIDEO_DISCOVERED",
                title=f"Phát hiện video mới từ {ch_name}",
                message=f"Đã cào được video mới: {title[:75]}...",
                level="INFO",
                target_role="CREATOR",
                metadata={
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "channel_name": ch_name,
                    "channel_url": ch_url,
                    "video_item_id": item_id,
                    "video_url": video_url,
                    "video_title": title,
                    "cover_url": cover_url,
                    "current_step": "Bóc tách & Tải về",
                },
            )
        except Exception as e:
            logger.debug(f"Lỗi notify_video_discovered: {e}")

    @classmethod
    async def notify_publish_success(
        cls,
        user_id: str,
        campaign_id: str,
        campaign_name: str,
        ch_name: str,
        ch_url: str,
        video_item_id: str,
        video_url: str,
        orig_title: str,
        trans_title: str,
        pub_pages: List[Dict[str, Any]],
        pub_yt: List[Dict[str, Any]],
        cover_url: Optional[str] = None,
    ):
        try:
            destinations = []
            for p in pub_pages:
                if p.get("success"):
                    destinations.append({
                        "platform": "facebook",
                        "target_name": p.get("page_name", "Fanpage"),
                        "post_url": p.get("reel_url"),
                        "status": "success",
                    })
            for y in pub_yt:
                if y.get("success"):
                    destinations.append({
                        "platform": "youtube",
                        "target_name": y.get("channel_title", "Kênh YouTube"),
                        "post_url": y.get("shorts_url"),
                        "status": "success",
                    })

            dest_names = ", ".join([d["target_name"] for d in destinations]) or "kênh đích"
            await cls.get_service().create_and_push(
                user_id=user_id,
                type="AUTO_PUBLISH_SUCCESS",
                title=f"Đã đăng thành công: {trans_title[:55]}...",
                message=f"Video từ kênh '{ch_name}' đã được xuất bản lên: {dest_names}.",
                level="SUCCESS",
                target_role="CREATOR",
                metadata={
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "channel_name": ch_name,
                    "channel_url": ch_url,
                    "video_item_id": video_item_id,
                    "video_url": video_url,
                    "video_title": orig_title,
                    "translated_title": trans_title,
                    "cover_url": cover_url,
                    "published_destinations": destinations,
                    "current_step": "Xuất bản hoàn tất",
                },
            )
        except Exception as e:
            logger.debug(f"Lỗi notify_publish_success: {e}")

    @classmethod
    async def notify_error_alert(
        cls,
        user_id: str,
        campaign_id: str,
        campaign_name: str,
        item_id: str,
        error_msg: str,
        ch_name: Optional[str] = None,
    ):
        try:
            await cls.get_service().create_and_push(
                user_id=user_id,
                type="AUTO_ERROR_ALERT",
                title=f"Cảnh báo lỗi: Chiến dịch {campaign_name}",
                message=f"Video {item_id} gặp sự cố: {error_msg[:120]}",
                level="ERROR",
                target_role="CREATOR",
                metadata={
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "channel_name": ch_name,
                    "video_item_id": item_id,
                    "error_detail": error_msg,
                },
            )
        except Exception as e:
            logger.debug(f"Lỗi notify_error_alert: {e}")

