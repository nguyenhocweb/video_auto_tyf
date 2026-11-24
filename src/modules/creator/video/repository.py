import logging
from typing import List, Dict, Any, Optional
from bson import ObjectId
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso

logger = logging.getLogger("video_download_repository")


class VideoDownloadMongoRepository:
    """Repository quản lý collection downloaded_videos trong MongoDB."""

    def __init__(self, db: Optional[Any] = None):
        self.db: Any = db or get_mongo_db()
        self.col: Any = self.db["downloaded_videos"]
        self.channel_col: Any = self.db["saved_channels"]

    @staticmethod
    def _format_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Chuẩn hóa dữ liệu Document MongoDB thành JSON-safe theo múi giờ Việt Nam (+07:00)."""
        doc["id"] = str(doc["_id"])
        doc["_id"] = str(doc["_id"])
        doc["user_id"] = str(doc.get("user_id", ""))
        doc["created_at"] = to_vn_iso(doc.get("created_at"))
        doc["updated_at"] = to_vn_iso(doc.get("updated_at"))
        return doc

    async def save_video(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu thông tin video đã tải vào thư viện người dùng."""
        now = get_vn_now()
        doc: Dict[str, Any] = {
            "user_id": data.get("user_id"),
            "item_id": data.get("item_id"),
            "title": data.get("title", "Video không tiêu đề"),
            "duration": data.get("duration", 0.0),
            "video_url": data.get("video_url"),
            "cover_url": data.get("cover_url"),
            "music_url": data.get("music_url"),
            "author_name": data.get("author_name", "Douyin Creator"),
            "author_avatar": data.get("author_avatar"),
            "cloudinary_url": data.get("cloudinary_url"),
            "source_platform": data.get("source_platform", "douyin"),
            "created_at": now,
            "updated_at": now,
        }
        res = await self.col.insert_one(doc)
        doc["_id"] = str(res.inserted_id)
        return self._format_doc(doc)

    async def get_user_videos(self, user_id: str, skip: int = 0, limit: int = 10) -> List[Dict[str, Any]]:
        """Lấy danh sách video của người dùng theo phân trang."""
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        cursor = self.col.find(user_q).sort("created_at", -1).skip(skip).limit(limit)
        items: List[Dict[str, Any]] = []
        async for doc in cursor:
            items.append(self._format_doc(doc))
        return items

    async def count_user_videos(self, user_id: str) -> int:
        """Đếm tổng số video của người dùng."""
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        return await self.col.count_documents(user_q)

    async def get_video_by_id(self, record_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết một video theo ID và user_id."""
        query_id = ObjectId(record_id) if ObjectId.is_valid(record_id) else record_id
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        doc = await self.col.find_one({"_id": query_id, **user_q})
        return self._format_doc(doc) if doc else None

    async def delete_video(self, record_id: str, user_id: str) -> bool:
        """Xóa bản ghi video khỏi thư viện cá nhân."""
        query_id = ObjectId(record_id) if ObjectId.is_valid(record_id) else record_id
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        res = await self.col.delete_one({"_id": query_id, **user_q})
        return res.deleted_count > 0

    async def save_channel(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu hoặc cập nhật thông tin kênh theo user_id (chỉ user này mới thấy)."""
        now = get_vn_now()
        channel_url = data.get("channel_url", "").strip()

        # Kiểm tra xem kênh này user đã lưu chưa, nếu đã lưu thì cập nhật tên
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        existing = await self.channel_col.find_one({"channel_url": channel_url, **user_q})

        if existing:
            update_data = {
                "name": data.get("name", existing.get("name")),
                "avatar_url": data.get("avatar_url") or existing.get("avatar_url"),
                "total_works": data.get("total_works", existing.get("total_works", 0)),
                "updated_at": now,
            }
            await self.channel_col.update_one({"_id": existing["_id"]}, {"$set": update_data})
            existing.update(update_data)
            return self._format_doc(existing)

        doc: Dict[str, Any] = {
            "user_id": user_id,
            "name": data.get("name", "Kênh Douyin"),
            "original_name": data.get("original_name", ""),
            "channel_url": channel_url,
            "avatar_url": data.get("avatar_url"),
            "total_works": data.get("total_works", 0),
            "created_at": now,
            "updated_at": now,
        }
        res = await self.channel_col.insert_one(doc)
        doc["_id"] = str(res.inserted_id)
        return self._format_doc(doc)

    async def get_user_channels(self, user_id: str) -> List[Dict[str, Any]]:
        """Lấy danh sách kênh mà user cụ thể đã lưu (cách ly hoàn toàn giữa các user)."""
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        cursor = self.channel_col.find(user_q).sort("updated_at", -1)
        items: List[Dict[str, Any]] = []
        async for doc in cursor:
            items.append(self._format_doc(doc))
        return items

    async def update_channel_name(self, channel_id: str, user_id: str, new_name: str) -> Optional[Dict[str, Any]]:
        """Cập nhật tên hiển thị của kênh theo user_id."""
        query_id = ObjectId(channel_id) if ObjectId.is_valid(channel_id) else channel_id
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        now = get_vn_now()
        res = await self.channel_col.find_one_and_update(
            {"_id": query_id, **user_q},
            {"$set": {"name": new_name.strip(), "updated_at": now}},
            return_document=True,
        )
        return self._format_doc(res) if res else None

    async def delete_channel(self, channel_id: str, user_id: str) -> bool:
        """Xóa kênh đã lưu của user."""
        query_id = ObjectId(channel_id) if ObjectId.is_valid(channel_id) else channel_id
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        res = await self.channel_col.delete_one({"_id": query_id, **user_q})
        return res.deleted_count > 0
