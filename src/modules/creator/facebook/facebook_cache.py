import logging
from typing import List, Optional
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso
from src.modules.creator.facebook.schemas import (
    FacebookPageItem,
    FacebookVideoItem,
    FacebookPostItem,
)

logger = logging.getLogger("facebook_cache")


class FacebookCache:
    """Quản lý lưu trữ và truy xuất cache Fanpages, Videos và Posts trên MongoDB."""

    @staticmethod
    async def get_cached_pages() -> List[FacebookPageItem]:
        pages: List[FacebookPageItem] = []
        try:
            db = get_mongo_db()
            cursor = db.facebook_pages.find({})
            async for doc in cursor:
                pages.append(
                    FacebookPageItem(
                        id=str(doc.get("id")),
                        name=doc.get("name", ""),
                        category=doc.get("category", "General"),
                        picture_url=doc.get("picture_url", ""),
                        fan_count=doc.get("fan_count", 0),
                        followers_count=doc.get("followers_count", 0),
                        access_token=doc.get("access_token", ""),
                    )
                )
        except Exception as ex:
            logger.warning(f"Lỗi đọc facebook_pages từ cache MongoDB: {ex}")
        return pages

    @staticmethod
    async def save_cached_pages(pages: List[FacebookPageItem]) -> None:
        try:
            db = get_mongo_db()
            now_iso = to_vn_iso(get_vn_now())
            for p in pages:
                data = p.model_dump()
                data["updated_at"] = now_iso
                await db.facebook_pages.update_one(
                    {"id": str(p.id)},
                    {"$set": data},
                    upsert=True,
                )
            logger.info(f"Đã lưu cache {len(pages)} Fanpage vào MongoDB.")
        except Exception as ex:
            logger.warning(f"Lỗi lưu facebook_pages vào MongoDB: {ex}")

    @staticmethod
    async def get_page_token(page_id: str) -> Optional[str]:
        try:
            db = get_mongo_db()
            doc = await db.facebook_pages.find_one({"id": str(page_id)})
            if doc and doc.get("access_token"):
                return doc.get("access_token")
        except Exception as ex:
            logger.debug(f"Lỗi tìm page token trong MongoDB: {ex}")
        return None

    @staticmethod
    async def get_cached_videos(page_id: str) -> List[FacebookVideoItem]:
        try:
            db = get_mongo_db()
            doc = await db.facebook_cached_videos.find_one({"page_id": str(page_id)})
            if doc and doc.get("videos"):
                return [FacebookVideoItem(**v) for v in doc["videos"]]
        except Exception as ex:
            logger.warning(f"Lỗi đọc cached videos của page {page_id}: {ex}")
        return []

    @staticmethod
    async def save_cached_videos(page_id: str, videos: List[FacebookVideoItem]) -> None:
        try:
            db = get_mongo_db()
            await db.facebook_cached_videos.update_one(
                {"page_id": str(page_id)},
                {
                    "$set": {
                        "page_id": str(page_id),
                        "videos": [v.model_dump() for v in videos],
                        "updated_at": to_vn_iso(get_vn_now()),
                    }
                },
                upsert=True,
            )
            logger.info(f"Đã lưu cache {len(videos)} video cho page {page_id}")
        except Exception as ex:
            logger.warning(f"Lỗi lưu cached videos: {ex}")

    @staticmethod
    async def get_cached_posts(page_id: str) -> List[FacebookPostItem]:
        try:
            db = get_mongo_db()
            doc = await db.facebook_cached_posts.find_one({"page_id": str(page_id)})
            if doc and doc.get("posts"):
                return [FacebookPostItem(**p) for p in doc["posts"]]
        except Exception as ex:
            logger.warning(f"Lỗi đọc cached posts của page {page_id}: {ex}")
        return []

    @staticmethod
    async def save_cached_posts(page_id: str, posts: List[FacebookPostItem]) -> None:
        try:
            db = get_mongo_db()
            await db.facebook_cached_posts.update_one(
                {"page_id": str(page_id)},
                {
                    "$set": {
                        "page_id": str(page_id),
                        "posts": [p.model_dump() for p in posts],
                        "updated_at": to_vn_iso(get_vn_now()),
                    }
                },
                upsert=True,
            )
            logger.info(f"Đã lưu cache {len(posts)} bài viết cho page {page_id}")
        except Exception as ex:
            logger.warning(f"Lỗi lưu cached posts: {ex}")

