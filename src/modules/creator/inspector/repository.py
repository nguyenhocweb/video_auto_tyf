import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from bson import ObjectId
from src.core.config import settings

logger = logging.getLogger("inspector_repository")
VN_TZ = timezone(timedelta(hours=7))


class InspectorMongoRepository:
    """Repository quản lý lưu trữ lịch sử thẩm định video & thumbnail."""

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        if db is not None:
            self.db = db
        else:
            client = AsyncIOMotorClient(settings.DATABASE_URL)
            self.db = client[settings.MONGO_DB_NAME]
        self.collection = self.db["inspector_records"]

    def _format_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Chuẩn hóa dữ liệu MongoDB sang dict an toàn cho Pydantic."""
        res = dict(doc)
        if "_id" in res:
            res["id"] = str(res.pop("_id"))

        for dt_field in ["created_at", "updated_at"]:
            if dt_field in res and isinstance(res[dt_field], datetime):
                dt_val: datetime = res[dt_field]
                if dt_val.tzinfo is None:
                    dt_val = dt_val.replace(tzinfo=timezone.utc)
                res[dt_field] = dt_val.astimezone(VN_TZ).isoformat()
        return res

    async def save_record(
        self,
        user_id: str,
        inspect_type: str,
        score: int,
        details: Dict[str, Any],
        summary: str,
    ) -> Dict[str, Any]:
        """Lưu kết quả thẩm định vào database."""
        now = datetime.now(timezone.utc)
        doc: Dict[str, Any] = {
            "user_id": user_id,
            "type": inspect_type,
            "score": score,
            "summary": summary,
            "details": details,
            "created_at": now,
            "updated_at": now,
        }
        res = await self.collection.insert_one(doc)
        doc["_id"] = res.inserted_id
        return self._format_doc(doc)

    async def get_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Lấy danh sách các lần thẩm định gần nhất của user."""
        cursor = self.collection.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self._format_doc(d) for d in docs]

