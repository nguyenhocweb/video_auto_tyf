from typing import Dict, Any, Optional, List
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso


class YouTubeMongoRepository:
    def __init__(self):
        self.db = get_mongo_db()
        self.channels_col = self.db["youtube_channels"]
        self.videos_col = self.db["youtube_uploaded_videos"]

    @staticmethod
    def _doc_to_dict(doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return {}
        res = dict(doc)
        if "_id" in res:
            res["id"] = str(res["_id"])
            del res["_id"]
        for k in ["created_at", "updated_at", "uploaded_at"]:
            if k in res and res[k]:
                res[k] = to_vn_iso(res[k])
        return res

    async def save_channel(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu hoặc cập nhật một Kênh YouTube theo (user_id, channel_id). Hỗ trợ nhiều kênh."""
        now = to_vn_iso(get_vn_now())
        ch_id = str(data["channel_id"])
        doc = {
            **data,
            "user_id": str(user_id),
            "updated_at": now,
        }
        res = await self.channels_col.find_one_and_update(
            {"user_id": str(user_id), "channel_id": ch_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=True,
        )
        return self._doc_to_dict(res)

    async def get_channels(self, user_id: str) -> List[Dict[str, Any]]:
        """Lấy tất cả các Kênh YouTube đã liên kết của người dùng."""
        cursor = self.channels_col.find({"user_id": str(user_id)}).sort("updated_at", -1)
        items = []
        async for doc in cursor:
            items.append(self._doc_to_dict(doc))
        return items

    async def get_channel(self, user_id: str, channel_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Lấy thông tin một Kênh cụ thể (hoặc kênh gần nhất nếu không truyền channel_id)."""
        query: Dict[str, Any] = {"user_id": str(user_id)}
        if channel_id:
            query["channel_id"] = str(channel_id)
        doc = await self.channels_col.find_one(query)
        return self._doc_to_dict(doc) if doc else None

    async def update_access_token(self, user_id: str, channel_id: str, access_token: str) -> None:
        """Cập nhật Access Token cho một kênh cụ thể."""
        await self.channels_col.update_one(
            {"user_id": str(user_id), "channel_id": str(channel_id)},
            {"$set": {"access_token": access_token.strip(), "updated_at": to_vn_iso(get_vn_now())}},
        )

    async def disconnect_channel(self, user_id: str, channel_id: Optional[str] = None) -> bool:
        """Hủy liên kết một Kênh YouTube cụ thể (hoặc toàn bộ kênh nếu không truyền id)."""
        query: Dict[str, Any] = {"user_id": str(user_id)}
        if channel_id:
            query["channel_id"] = str(channel_id)
        res = await self.channels_col.delete_one(query) if channel_id else await self.channels_col.delete_many(query)
        return res.deleted_count > 0

    async def record_uploaded_video(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        now = to_vn_iso(get_vn_now())
        doc = {
            **data,
            "user_id": str(user_id),
            "uploaded_at": now,
        }
        res = await self.videos_col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return self._doc_to_dict(doc)

    async def get_uploaded_videos(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.videos_col.find({"user_id": str(user_id)}).sort("uploaded_at", -1).limit(limit)
        items = []
        async for doc in cursor:
            items.append(self._doc_to_dict(doc))
        return items

    async def mark_video_deleted_from_youtube(
        self, user_id: str, video_id: str, channel_id: Optional[str] = None
    ) -> None:
        """Đánh dấu video đã bị xóa khỏi YouTube, giữ lại DB để chống cào/đăng lại."""
        now = to_vn_iso(get_vn_now())
        await self.videos_col.update_many(
            {"user_id": str(user_id), "video_id": str(video_id)},
            {
                "$set": {
                    "status": "deleted_from_youtube",
                    "is_deleted_from_youtube": True,
                    "deleted_at": now,
                    "updated_at": now,
                }
            },
        )
        posted_col = self.db["posted_videos"]
        await posted_col.update_many(
            {"user_id": str(user_id), "published_youtube_channels.video_id": str(video_id)},
            {
                "$set": {
                    "published_youtube_channels.$.status": "deleted_from_youtube",
                    "published_youtube_channels.$.deleted_at": now,
                    "is_blacklisted": True,
                }
            },
        )

    async def get_deleted_video_ids(self, user_id: str) -> set:
        """Lấy danh sách các video_id đã bị xóa trên YouTube của user."""
        cursor = self.videos_col.find(
            {"user_id": str(user_id), "is_deleted_from_youtube": True},
            {"video_id": 1},
        )
        s = set()
        async for doc in cursor:
            vid = doc.get("video_id")
            if vid:
                s.add(str(vid))
        return s
