import logging
from typing import Dict, Any, Optional, List
from src.core.utils.video_resolver import resolve_local_video_path
from src.core.engines.youtube.youtube_publisher import YouTubePublisher
from src.modules.creator.youtube.repository import YouTubeMongoRepository
from src.modules.creator.youtube.schemas import (
    YouTubeChannelItem,
    YouTubeChannelListResponse,
    YouTubeChannelResponse,
    YouTubeVideoItem,
    YouTubeVideoListResponse,
    AvailableVideoItem,
    PublishShortsRequest,
    PublishShortsResponse,
    DeleteYouTubeVideoResponse,
)

logger = logging.getLogger("youtube_service")


class YouTubeService:
    def __init__(self, repo: Optional[YouTubeMongoRepository] = None):
        self.repo = repo or YouTubeMongoRepository()

    def get_auth_url(self, user_id: str) -> str:
        """Tạo đường link xác thực OAuth 2.0 có gắn state là user_id."""
        return YouTubePublisher.get_auth_url(state=user_id)

    async def handle_callback(self, code: str, user_id: str) -> Dict[str, Any]:
        """Nhận Authorization Code từ Google, lấy Refresh Token và lưu Kênh (hỗ trợ nhiều kênh)."""
        tokens = await YouTubePublisher.exchange_code_for_tokens(code)
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in", 3600)

        if not access_token:
            raise ValueError("Không nhận được access_token từ Google.")

        ch_info = await YouTubePublisher.get_my_channel(access_token)
        google_email = await YouTubePublisher.get_google_user_email(access_token)
        doc_data = {
            "channel_id": ch_info["channel_id"],
            "channel_title": ch_info["title"],
            "custom_url": ch_info.get("custom_url"),
            "avatar_url": ch_info.get("avatar_url"),
            "subscriber_count": ch_info.get("subscriber_count", 0),
            "video_count": ch_info.get("video_count", 0),
            "access_token": access_token,
            "expires_in": expires_in,
            "google_email": google_email,
        }
        if refresh_token:
            doc_data["refresh_token"] = refresh_token

        saved = await self.repo.save_channel(user_id=user_id, data=doc_data)
        logger.info(f"Đã lưu thành công Kênh YouTube '{ch_info['title']}' cho user {user_id}")
        return saved

    async def get_channels(self, user_id: str) -> YouTubeChannelListResponse:
        """Lấy danh sách tất cả các Kênh YouTube đã liên kết."""
        channels_data = await self.repo.get_channels(user_id)
        items = [
            YouTubeChannelItem(
                id=c.get("id"),
                channel_id=str(c.get("channel_id") or ""),
                channel_title=str(c.get("channel_title") or "Kênh YouTube"),
                google_email=c.get("google_email"),
                custom_url=c.get("custom_url"),
                avatar_url=c.get("avatar_url"),
                subscriber_count=int(c.get("subscriber_count") or 0),
                video_count=int(c.get("video_count") or 0),
                has_refresh_token=bool(c.get("refresh_token")),
                created_at=c.get("created_at"),
                updated_at=c.get("updated_at"),
            )
            for c in channels_data
        ]
        return YouTubeChannelListResponse(total=len(items), channels=items)

    async def get_valid_access_token(self, user_id: str, channel_id: Optional[str] = None) -> str:
        """Lấy Access Token hợp lệ của một kênh, tự động làm mới bằng Refresh Token nếu cần."""
        ch = await self.repo.get_channel(user_id, channel_id)
        if not ch:
            target_desc = f" ({channel_id})" if channel_id else ""
            raise ValueError(f"Không tìm thấy Kênh YouTube{target_desc} đã liên kết.")

        refresh_tok = ch.get("refresh_token")
        acc_tok = ch.get("access_token")
        target_channel_id = ch.get("channel_id")

        if refresh_tok:
            try:
                ref_res = await YouTubePublisher.refresh_access_token(refresh_tok)
                new_acc = ref_res.get("access_token")
                if new_acc and target_channel_id:
                    await self.repo.update_access_token(user_id, target_channel_id, new_acc)
                    return new_acc
            except Exception as e:
                logger.warning(f"Lỗi refresh token YouTube kênh {target_channel_id}: {e}")

        if acc_tok:
            return acc_tok

        raise ValueError(f"Token Kênh YouTube {target_channel_id} đã hết hạn và không thể tự động làm mới.")

    async def get_channel_status(self, user_id: str) -> YouTubeChannelResponse:
        """Kiểm tra trạng thái Kênh đầu tiên (Backward compatible)."""
        ch = await self.repo.get_channel(user_id)
        if not ch:
            return YouTubeChannelResponse(is_connected=False)

        return YouTubeChannelResponse(
            is_connected=True,
            channel_id=ch.get("channel_id"),
            channel_title=ch.get("channel_title"),
            google_email=ch.get("google_email"),
            custom_url=ch.get("custom_url"),
            avatar_url=ch.get("avatar_url"),
            subscriber_count=ch.get("subscriber_count", 0),
            video_count=ch.get("video_count", 0),
            has_refresh_token=bool(ch.get("refresh_token")),
        )

    async def publish_shorts(self, user_id: str, req: PublishShortsRequest) -> PublishShortsResponse:
        """Xuất bản một video lên Kênh YouTube Shorts được chỉ định."""
        try:
            acc_token = await self.get_valid_access_token(user_id, req.channel_id)
            target_path = req.video_path or req.video_url
            if not target_path:
                raise ValueError("Thiếu đường dẫn file video để tải lên.")

            resolved_path = await resolve_local_video_path(target_path)
            v_type = getattr(req, "video_type", "video") or "video"
            res = await YouTubePublisher.upload_shorts(
                access_token=acc_token,
                video_path=resolved_path,
                title=req.title,
                description=req.description or "",
                tags=req.tags,
                privacy_status=req.privacy_status or "public",
                video_type=v_type,
            )

            await self.repo.record_uploaded_video(
                user_id=user_id,
                data={
                    "channel_id": req.channel_id,
                    "video_id": res["video_id"],
                    "shorts_url": res["shorts_url"],
                    "watch_url": res.get("watch_url"),
                    "title": res["title"],
                    "privacy_status": res["status"],
                    "video_type": v_type,
                },
            )

            return PublishShortsResponse(
                success=True,
                channel_id=req.channel_id,
                video_id=res["video_id"],
                shorts_url=res["shorts_url"],
                watch_url=res.get("watch_url"),
                video_url=res.get("video_url"),
                video_type=v_type,
                title=res["title"],
            )
        except Exception as e:
            logger.error(f"Lỗi xuất bản YouTube Shorts kênh {req.channel_id}: {e}")
            return PublishShortsResponse(success=False, channel_id=req.channel_id, error=str(e))

    async def disconnect(self, user_id: str, channel_id: Optional[str] = None) -> bool:
        """Hủy liên kết một Kênh YouTube (hoặc toàn bộ kênh)."""
        return await self.repo.disconnect_channel(user_id, channel_id)

    async def get_channel_videos(
        self, user_id: str, channel_id: Optional[str] = None, limit: int = 25
    ) -> YouTubeVideoListResponse:
        """Lấy danh sách video của Kênh YouTube kèm trạng thái đã xóa DB."""
        try:
            acc_tok = await self.get_valid_access_token(user_id, channel_id)
            raw_vids = await YouTubePublisher.get_channel_videos(
                access_token=acc_tok, channel_id=channel_id, max_results=limit
            )
            deleted_ids = await self.repo.get_deleted_video_ids(user_id)
            items = []
            for v in raw_vids:
                is_del = v.get("id") in deleted_ids
                items.append(YouTubeVideoItem(**v, is_deleted=is_del))
            return YouTubeVideoListResponse(total=len(items), videos=items)
        except Exception as e:
            logger.error(f"Lỗi lấy video kênh {channel_id}: {e}")
            return YouTubeVideoListResponse(total=0, videos=[])

    async def delete_video(
        self, user_id: str, channel_id: str, video_id: str
    ) -> DeleteYouTubeVideoResponse:
        """Xóa video vĩnh viễn trên YouTube qua API và cập nhật DB để chống cào lại."""
        acc_tok = await self.get_valid_access_token(user_id, channel_id)
        await YouTubePublisher.delete_video(acc_tok, video_id)
        await self.repo.mark_video_deleted_from_youtube(user_id, video_id, channel_id)
        return DeleteYouTubeVideoResponse(
            success=True,
            video_id=video_id,
            message=f"Đã xóa video {video_id} khỏi kênh YouTube thành công và lưu vết chống cào lại.",
            blacklisted=True,
        )

    @staticmethod
    def get_available_rendered_videos() -> List[AvailableVideoItem]:
        """Quét kho lưu trữ video đã làm sạch / Dubbing để người dùng chọn đăng Shorts 1-Click."""
        from src.modules.creator.facebook.service import FacebookService
        fb_vids = FacebookService.get_available_rendered_videos()
        return [
            AvailableVideoItem(
                filename=getattr(v, "name", getattr(v, "filename", "")),
                path=v.path,
                title=getattr(v, "name", getattr(v, "title", "")),
                size_mb=v.size_mb,
                created_at=getattr(v, "modified_time", getattr(v, "created_at", "")),
                source_type=getattr(v, "source", getattr(v, "source_type", "")),
            )
            for v in fb_vids
        ]
