from typing import Dict, Any, Optional, List
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso


class TikTokMongoRepository:
    """Repository quản lý các kênh TikTok liên kết và nhật ký xuất bản video."""

    def __init__(self):
        self.db = get_mongo_db()
        self.channels_col = self.db["tiktok_channels"]
        self.videos_col = self.db["tiktok_uploaded_videos"]

    @staticmethod
    def _doc_to_dict(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
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
        """Lưu hoặc cập nhật thông tin Kênh TikTok theo (user_id, channel_id). Hỗ trợ đa kênh."""
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
        """Lấy danh sách tất cả các Kênh TikTok đã liên kết của người dùng."""
        cursor = self.channels_col.find({"user_id": str(user_id)}).sort("updated_at", -1)
        items = []
        async for doc in cursor:
            items.append(self._doc_to_dict(doc))
        return items

    async def get_channel(self, user_id: str, channel_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết một Kênh TikTok cụ thể (hoặc kênh mới nhất nếu không truyền id)."""
        query: Dict[str, Any] = {"user_id": str(user_id)}
        if channel_id:
            query["channel_id"] = str(channel_id)
        doc = await self.channels_col.find_one(query)
        return self._doc_to_dict(doc) if doc else None

    async def update_tokens(
        self,
        user_id: str,
        channel_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> None:
        """Cập nhật Access Token và Refresh Token cho kênh."""
        now = to_vn_iso(get_vn_now())
        update_fields: Dict[str, Any] = {
            "access_token": access_token.strip(),
            "updated_at": now,
        }
        if refresh_token:
            update_fields["refresh_token"] = refresh_token.strip()
        if expires_in:
            update_fields["token_expires_in"] = expires_in

        await self.channels_col.update_one(
            {"user_id": str(user_id), "channel_id": str(channel_id)},
            {"$set": update_fields},
        )

    async def disconnect_channel(self, user_id: str, channel_id: Optional[str] = None) -> bool:
        """Hủy liên kết một Kênh TikTok (hoặc toàn bộ kênh nếu không truyền id)."""
        query: Dict[str, Any] = {"user_id": str(user_id)}
        if channel_id:
            query["channel_id"] = str(channel_id)
        res = await self.channels_col.delete_one(query) if channel_id else await self.channels_col.delete_many(query)
        return res.deleted_count > 0

    async def record_uploaded_video(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ghi nhận lịch sử video đã được đăng lên TikTok."""
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
        """Lấy danh sách video đã đăng lên TikTok của người dùng."""
        cursor = self.videos_col.find({"user_id": str(user_id)}).sort("uploaded_at", -1).limit(limit)
        items = []
        async for doc in cursor:
            items.append(self._doc_to_dict(doc))
        return items
