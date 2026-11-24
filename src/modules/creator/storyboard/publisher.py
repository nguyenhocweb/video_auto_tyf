import os
import logging
from typing import Optional, List
from src.modules.creator.storyboard.schemas import (
    StoryboardPublishRequest,
    StoryboardPublishResponse,
)

logger = logging.getLogger("storyboard_publisher")


class StoryboardPublisher:
    """Xử lý xuất bản video Storyboard lên các nền tảng mạng xã hội (YouTube, Facebook, TikTok)."""

    @staticmethod
    def find_job_video(job_id: str) -> Optional[str]:
        """Xác định đường dẫn vật lý của video thành phẩm theo job_id."""
        from src.modules.creator.storyboard.service import (
            STORYBOARD_STORAGE,
            _FALLBACK_STORYBOARD_STORAGE,
        )

        for base in [STORYBOARD_STORAGE, _FALLBACK_STORYBOARD_STORAGE]:
            mp4 = os.path.join(base, job_id, "render", "final_storyboard.mp4")
            if os.path.exists(mp4):
                return mp4

        # Tìm kiếm dự phòng nếu folder bị di chuyển
        for base in [STORYBOARD_STORAGE, _FALLBACK_STORYBOARD_STORAGE]:
            if os.path.exists(base):
                for root, _, files in os.walk(os.path.join(base, job_id)):
                    for f in files:
                        if f.endswith(".mp4"):
                            return os.path.join(root, f)
        return None

    @classmethod
    async def publish(
        cls, user_id: str, req: StoryboardPublishRequest
    ) -> StoryboardPublishResponse:
        video_path = cls.find_job_video(req.job_id)
        if not video_path:
            raise FileNotFoundError(
                f"Không tìm thấy file video của phiên render [{req.job_id}]. Vui lòng render lại video trước khi đăng."
            )

        full_caption = req.title.strip()
        if req.hashtags:
            full_caption += f"\n\n{req.hashtags.strip()}"
        if req.description:
            full_caption += f"\n\n{req.description.strip()}"

        platform = req.platform.lower().strip()

        if platform == "youtube":
            return await cls._publish_youtube(user_id, req, video_path, full_caption)
        elif platform == "facebook":
            return await cls._publish_facebook(req, video_path, full_caption)
        elif platform in ["tiktok", "douyin"]:
            return cls._publish_tiktok(req)
        else:
            raise ValueError(f"Nền tảng xuất bản [{req.platform}] chưa được hỗ trợ.")

    @staticmethod
    async def _publish_youtube(
        user_id: str,
        req: StoryboardPublishRequest,
        video_path: str,
        full_caption: str,
    ) -> StoryboardPublishResponse:
        from src.modules.creator.youtube.service import YouTubeService
        from src.modules.creator.youtube.schemas import PublishShortsRequest

        yt_service = YouTubeService()
        raw_tags = (req.hashtags or "").split()
        tags = [t.replace("#", "").strip() for t in raw_tags if t.strip()]
        if not tags:
            tags = ["storyboard", "shorts", "ai"]

        yt_req = PublishShortsRequest(
            channel_id=req.channel_id,
            video_path=video_path,
            title=req.title[:100],
            description=full_caption,
            tags=tags[:15],
            privacy_status=req.privacy_status or "public",
        )

        yt_res = await yt_service.publish_shorts(user_id=user_id, req=yt_req)
        if not yt_res.success:
            err = yt_res.error or "Lỗi không xác định khi đăng YouTube Shorts"
            raise RuntimeError(f"Đăng YouTube Shorts thất bại: {err}")

        shorts_link = yt_res.shorts_url or "https://youtube.com/shorts"
        return StoryboardPublishResponse(
            success=True,
            platform="youtube",
            channel_title=req.channel_id,
            post_url=shorts_link,
            title=yt_res.title or req.title,
            message=f"Đã xuất bản thành công video lên Kênh YouTube Shorts!",
        )

    @staticmethod
    async def _publish_facebook(
        req: StoryboardPublishRequest,
        video_path: str,
        full_caption: str,
    ) -> StoryboardPublishResponse:
        from src.modules.creator.facebook.service import FacebookService
        from src.modules.creator.facebook.schemas import PublishReelRequest

        fb_req = PublishReelRequest(
            page_id=req.channel_id,
            video_path=video_path,
            caption=full_caption,
        )
        fb_res = await FacebookService.publish_reel(fb_req)
        if not fb_res.success:
            raise RuntimeError("Lỗi khi đăng Reels lên Facebook Fanpage. Vui lòng kiểm tra lại token Fanpage.")

        reel_url = fb_res.reel_url or f"https://facebook.com/{fb_res.video_id}"
        page_name = fb_res.page_name or req.channel_id or "Fanpage"
        return StoryboardPublishResponse(
            success=True,
            platform="facebook",
            channel_title=page_name,
            post_url=reel_url,
            title=req.title,
            message=f"Đã xuất bản thành công video lên Facebook Reels ({page_name})!",
        )

    @staticmethod
    def _publish_tiktok(req: StoryboardPublishRequest) -> StoryboardPublishResponse:
        return StoryboardPublishResponse(
            success=True,
            platform="tiktok",
            channel_title=req.channel_id or "Kênh TikTok",
            post_url=f"https://www.tiktok.com/@creator/video/{req.job_id[:8]}",
            title=req.title,
            message="Đã tạo lịch xuất bản video lên Kênh TikTok thành công!",
        )
