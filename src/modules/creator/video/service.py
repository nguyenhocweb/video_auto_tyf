import sys
import re
import math
import asyncio
import logging
from typing import Optional, Dict, Any
from src.modules.creator.video.schemas import (
    VideoMetadataResponse,
    VideoSaveRequest,
    VideoRecordResponse,
    VideoPaginationResponse,
    ChannelTodayVideosResponse,
    SavedChannelCreateRequest,
    SavedChannelResponse,
    SavedChannelListResponse,
)
from src.core.engines.douyin import DouyinExtractor, DouyinChannelCrawler
from src.modules.creator.video.repository import VideoDownloadMongoRepository
from src.modules.shared.cloudinary.service import FastCloudinaryService

logger = logging.getLogger("video_download_service")


def _run_crawler_in_proactor(channel_url: str, limit: int) -> Dict[str, Any]:
    """Chạy DouyinChannelCrawler trong ProactorEventLoop riêng biệt để tương thích 100% Windows Uvicorn."""
    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(DouyinChannelCrawler.crawl_today_videos(channel_url, limit=limit))
    finally:
        loop.close()


class VideoDownloadService:
    def __init__(self, repo: Optional[VideoDownloadMongoRepository] = None):
        self.repo = repo or VideoDownloadMongoRepository()

    async def extract_douyin(self, raw_text: str) -> VideoMetadataResponse:
        """Trích xuất metadata video Douyin không dính logo watermark."""
        raw_data = await DouyinExtractor.extract_no_watermark_video(raw_text)
        return VideoMetadataResponse(**raw_data)

    async def crawl_channel_today(
        self, channel_url: str, limit: int = 20
    ) -> ChannelTodayVideosResponse:
        """Quét và trích xuất danh sách video mới nhất của kênh, tự động dịch tên kênh."""
        if sys.platform == "win32":
            loop = asyncio.get_running_loop()
            crawl_data = await loop.run_in_executor(
                None, _run_crawler_in_proactor, channel_url, limit
            )
        else:
            crawl_data = await DouyinChannelCrawler.crawl_today_videos(channel_url, limit=limit)

        # Lấy active API keys bất đồng bộ từ DB (tránh lỗi cross-thread event loop của Motor)
        groq_keys = []
        gemini_keys = []
        try:
            from src.modules.creator.dubbing.groq_keys_repository import GroqKeysMongoRepository
            from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository
            groq_keys = await GroqKeysMongoRepository().get_active_keys()
            gemini_keys = await GeminiKeysMongoRepository().get_active_keys()
        except Exception as ke:
            logger.debug(f"Không thể lấy API keys từ DB: {ke}")

        # Tự động dịch tên kênh (Đa tầng: LLM -> Google GTX -> Hán-Việt Dictionary)
        raw_creator_name = crawl_data.get("creator_name", "Douyin Creator")
        from src.modules.creator.video.channel_translator import ChannelMetadataTranslator
        translated_name = await ChannelMetadataTranslator.translate_channel_name(
            raw_creator_name, groq_keys=groq_keys, gemini_keys=gemini_keys
        )
        crawl_data["translated_name"] = translated_name

        # Dịch nhanh tiêu đề danh sách video mới quét để người dùng dễ theo dõi
        videos = crawl_data.get("videos", [])
        if videos:
            try:
                titles_to_trans = [v.get("title", "") for v in videos[:15]]
                translated_titles = await ChannelMetadataTranslator.translate_video_titles(
                    titles_to_trans, groq_keys=groq_keys, gemini_keys=gemini_keys
                )
                for idx, t_title in enumerate(translated_titles):
                    if t_title and t_title.strip() and idx < len(videos):
                        videos[idx]["title"] = t_title
            except Exception as te:
                logger.debug(f"Không thể dịch tiêu đề video: {te}")

        return ChannelTodayVideosResponse(**crawl_data)

    async def save_video_to_library(
        self, user_id: str, payload: VideoSaveRequest
    ) -> VideoRecordResponse:
        """Lưu trữ video vào thư viện người dùng và đồng bộ lên Cloudinary."""
        cloudinary_url = None
        try:
            # Upload video lên Cloudinary nếu khả dụng
            cloud_res = await FastCloudinaryService.upload_video_from_url(
                video_url=payload.video_url,
                public_id=f"douyin_{payload.item_id}_{user_id[:6]}",
                folder="video_ai/downloaded_videos",
            )
            if cloud_res:
                cloudinary_url = cloud_res.get("secure_url")
        except Exception as e:
            logger.warning(f"Lỗi khi upload Cloudinary video: {e}")

        # Chuẩn bị bản ghi lưu MongoDB
        doc_data = {
            "user_id": user_id,
            "item_id": payload.item_id,
            "title": payload.title,
            "duration": payload.duration,
            "video_url": payload.video_url,
            "cover_url": payload.cover_url,
            "music_url": payload.music_url,
            "author_name": payload.author_name,
            "author_avatar": payload.author_avatar,
            "cloudinary_url": cloudinary_url,
            "source_platform": "douyin",
        }

        saved_doc = await self.repo.save_video(doc_data)
        return VideoRecordResponse(
            id=saved_doc["id"],
            user_id=saved_doc["user_id"],
            item_id=saved_doc["item_id"],
            title=saved_doc["title"],
            duration=saved_doc["duration"],
            video_url=saved_doc["video_url"],
            cover_url=saved_doc.get("cover_url"),
            music_url=saved_doc.get("music_url"),
            author_name=saved_doc.get("author_name"),
            author_avatar=saved_doc.get("author_avatar"),
            cloudinary_url=saved_doc.get("cloudinary_url"),
            created_at=saved_doc["created_at"].isoformat()
            if hasattr(saved_doc["created_at"], "isoformat")
            else str(saved_doc["created_at"]),
        )

    async def get_user_history(
        self, user_id: str, page: int = 1, limit: int = 10
    ) -> VideoPaginationResponse:
        """Lấy danh sách video đã lưu của người dùng có phân trang."""
        page = max(1, page)
        limit = max(1, min(limit, 50))
        skip = (page - 1) * limit

        total = await self.repo.count_user_videos(user_id)
        raw_items = await self.repo.get_user_videos(user_id, skip=skip, limit=limit)
        total_pages = max(1, math.ceil(total / limit))

        items = [
            VideoRecordResponse(
                id=item["id"],
                user_id=item["user_id"],
                item_id=item["item_id"],
                title=item.get("title", ""),
                duration=item.get("duration", 0.0),
                video_url=item.get("video_url", ""),
                cover_url=item.get("cover_url"),
                music_url=item.get("music_url"),
                author_name=item.get("author_name"),
                author_avatar=item.get("author_avatar"),
                cloudinary_url=item.get("cloudinary_url"),
                created_at=str(item.get("created_at", "")),
            )
            for item in raw_items
        ]

        return VideoPaginationResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    async def delete_record(self, user_id: str, record_id: str) -> bool:
        """Xóa bản ghi video khỏi thư viện cá nhân."""
        return await self.repo.delete_video(record_id, user_id)

    async def save_channel(
        self, user_id: str, payload: SavedChannelCreateRequest
    ) -> SavedChannelResponse:
        """Lưu kênh vào database cho riêng user này."""
        doc = await self.repo.save_channel(
            user_id,
            {
                "name": payload.name,
                "original_name": payload.original_name,
                "channel_url": payload.channel_url,
                "avatar_url": payload.avatar_url,
                "total_works": payload.total_works,
            },
        )
        return SavedChannelResponse(**doc)

    async def get_saved_channels(self, user_id: str) -> SavedChannelListResponse:
        """Lấy danh sách các kênh đã lưu của user, tự động chuyển ngữ Hán-Việt nếu tên còn chữ Hán."""
        docs = await self.repo.get_user_channels(user_id)
        from src.modules.creator.video.channel_translator import ChannelMetadataTranslator
        for d in docs:
            c_name = d.get("name", "")
            if re.search(r"[\u4e00-\u9fff]", c_name):
                orig = d.get("original_name") or c_name
                d["original_name"] = orig
                trans = ChannelMetadataTranslator.to_sino_vietnamese(c_name)
                if trans and not re.search(r"[\u4e00-\u9fff]", trans):
                    d["name"] = trans
        channels = [SavedChannelResponse(**d) for d in docs]
        return SavedChannelListResponse(channels=channels, total=len(channels))

    async def update_saved_channel_name(
        self, channel_id: str, user_id: str, new_name: str
    ) -> Optional[SavedChannelResponse]:
        """Đổi tên kênh đã lưu của user."""
        doc = await self.repo.update_channel_name(channel_id, user_id, new_name)
        return SavedChannelResponse(**doc) if doc else None

    async def delete_saved_channel(self, channel_id: str, user_id: str) -> bool:
        """Xóa kênh đã lưu của user."""
        return await self.repo.delete_channel(channel_id, user_id)

