import datetime
from bson import ObjectId
from typing import List, Dict, Any, Optional
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso


class NotificationMongoRepository:
    def __init__(self):
        self.db = get_mongo_db()
        self.col = self.db["notifications"]

    @staticmethod
    def _doc_to_dict(doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return {}
        res = dict(doc)
        if "_id" in res:
            res["id"] = str(res["_id"])
            del res["_id"]
        for k in ["created_at", "read_at"]:
            if k in res and res[k]:
                res[k] = to_vn_iso(res[k])
        return res

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc = dict(data)
        doc["is_read"] = False
        doc["read_at"] = None
        doc["created_at"] = to_vn_iso(get_vn_now())
        res = await self.col.insert_one(doc)
        doc["id"] = str(res.inserted_id)
        if "_id" in doc:
            del doc["_id"]
        return doc

    async def get_user_notifications(
        self,
        user_id: str,
        role: str = "USER",
        is_read: Optional[bool] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        is_admin = role.upper() in ["ADMIN", "SUPER ADMIN"]
        role_filter = {"$in": ["ALL", "ADMIN", "CREATOR"]} if is_admin else {"$in": ["ALL", "CREATOR"]}

        query: Dict[str, Any] = {
            "$or": [
                {"user_id": str(user_id)},
                {"user_id": None, "target_role": role_filter},
                {"user_id": {"$exists": False}, "target_role": role_filter},
            ]
        }
        if is_read is not None:
            query["is_read"] = is_read

        cursor = self.col.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = []
        async for doc in cursor:
            items.append(self._doc_to_dict(doc))
        return items

    async def get_unread_count(self, user_id: str, role: str = "USER") -> int:
        is_admin = role.upper() in ["ADMIN", "SUPER ADMIN"]
        role_filter = {"$in": ["ALL", "ADMIN", "CREATOR"]} if is_admin else {"$in": ["ALL", "CREATOR"]}

        query: Dict[str, Any] = {
            "is_read": False,
            "$or": [
                {"user_id": str(user_id)},
                {"user_id": None, "target_role": role_filter},
                {"user_id": {"$exists": False}, "target_role": role_filter},
            ],
        }
        return await self.col.count_documents(query)

    async def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        now = to_vn_iso(get_vn_now())
        res = await self.col.update_one(
            {"_id": ObjectId(notification_id)},
            {"$set": {"is_read": True, "read_at": now}},
        )
        return res.modified_count > 0

    async def mark_all_as_read(self, user_id: str) -> int:
        now = to_vn_iso(get_vn_now())
        query = {
            "is_read": False,
            "$or": [{"user_id": str(user_id)}, {"user_id": None}, {"user_id": {"$exists": False}}],
        }
        res = await self.col.update_many(query, {"$set": {"is_read": True, "read_at": now}})
        return res.modified_count

    async def delete(self, notification_id: str, user_id: str) -> bool:
        res = await self.col.delete_one({"_id": ObjectId(notification_id)})
        return res.deleted_count > 0

    async def cleanup_old(self, keep_days: int = 30) -> int:
        cutoff = to_vn_iso(get_vn_now() - datetime.timedelta(days=keep_days))
        res = await self.col.delete_many({"created_at": {"$lte": cutoff}})
        return res.deleted_count

