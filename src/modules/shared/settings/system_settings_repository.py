import datetime
from typing import Dict, Any, Optional
from src.core.database_mongo import get_mongo_db


class SystemSettingsMongoRepository:
    """Quản lý các cấu hình động của toàn hệ thống (Hàng đợi, giới hạn RAM, tải song song)."""

    def __init__(self, db: Optional[Any] = None):
        self.db: Any = db or get_mongo_db()
        self.col: Any = self.db["system_settings"]

    async def get_concurrency_settings(self) -> Dict[str, Any]:
        """Lấy cấu hình số luồng chạy song song và RAM máy chủ."""
        doc = await self.col.find_one({"setting_key": "voice_concurrency"})
        if not doc:
            # Mặc định an toàn cho máy chủ 16GB RAM: 2 luồng song song
            default_doc = {
                "setting_key": "voice_concurrency",
                "max_concurrency": 2,
                "server_ram_gb": 16,
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            }
            res = await self.col.insert_one(default_doc)
            default_doc["_id"] = str(res.inserted_id)
            return default_doc

        doc["_id"] = str(doc["_id"])
        return doc

    async def update_concurrency_settings(
        self, max_concurrency: int, server_ram_gb: Optional[int] = None
    ) -> Dict[str, Any]:
        """Cập nhật cấu hình hàng đợi song song."""
        now = datetime.datetime.now(datetime.timezone.utc)
        updates: Dict[str, Any] = {
            "max_concurrency": max(1, min(max_concurrency, 64)),
            "updated_at": now,
        }
        if server_ram_gb:
            updates["server_ram_gb"] = max(4, min(server_ram_gb, 512))

        await self.col.update_one(
            {"setting_key": "voice_concurrency"},
            {"$set": updates},
            upsert=True,
        )
        return await self.get_concurrency_settings()
