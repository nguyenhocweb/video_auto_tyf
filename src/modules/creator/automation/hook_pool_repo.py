import os
import uuid
import logging
from typing import Dict, Any, Optional
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso

logger = logging.getLogger("hook_pool_repo")


class HookPoolMongoRepository:
    """Quản lý kho đệm các đoạn Hook đã cắt của Kênh Nguồn 1 trong MongoDB."""

    def __init__(self):
        self.db = get_mongo_db()
        self.col = self.db["automation_hook_pools"]

    async def is_hook_already_saved(self, campaign_id: str, item_id: str) -> bool:
        """Kiểm tra video Hook này đã từng được cào và lưu kho chưa."""
        doc = await self.col.find_one({
            "campaign_id": campaign_id,
            "item_id": str(item_id),
        })
        return doc is not None

    async def save_hook(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu một đoạn Hook đã cắt thành công vào kho đệm."""
        now_str = to_vn_iso(get_vn_now())
        doc = {
            "id": data.get("id") or str(uuid.uuid4()),
            "campaign_id": data["campaign_id"],
            "user_id": data.get("user_id", "default_user"),
            "item_id": str(data["item_id"]),
            "video_url": data.get("video_url", ""),
            "title": data.get("title", ""),
            "hook_path": str(data["hook_path"]),
            "duration": float(data.get("duration", 0.0)),
            "status": "available",  # available | used
            "used_count": 0,
            "used_in_videos": [],
            "created_at": now_str,
            "updated_at": now_str,
        }
        await self.col.insert_one(doc)
        logger.info(f"Đã lưu Hook [{doc['item_id']}] vào kho đệm chiến dịch [{doc['campaign_id']}]")
        return doc

    async def get_available_hook(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Lấy một Hook mới nhất đang ở trạng thái 'available' và file còn tồn tại trên đĩa."""
        cursor = self.col.find({
            "campaign_id": campaign_id,
            "status": "available",
        }).sort("created_at", -1)

        async for doc in cursor:
            hook_path = doc.get("hook_path")
            if hook_path and os.path.exists(hook_path):
                return doc
            else:
                await self.col.update_one({"id": doc["id"]}, {"$set": {"status": "missing"}})
        return None

    async def get_fallback_hook(self, campaign_id: str, policy: str = "reuse_oldest") -> Optional[Dict[str, Any]]:
        """Lấy Hook dự phòng khi kho hết Hook mới (ưu tiên Hook có used_count thấp nhất)."""
        if policy != "reuse_oldest":
            return None

        cursor = self.col.find({
            "campaign_id": campaign_id,
            "status": "used",
        }).sort([("used_count", 1), ("updated_at", 1)])

        async for doc in cursor:
            hook_path = doc.get("hook_path")
            if hook_path and os.path.exists(hook_path):
                return doc
        return None

    async def mark_hook_used(self, hook_id: str, target_video_item_id: str) -> None:
        """Đánh dấu Hook đã được ghép vào một video thân bài cụ thể."""
        now_str = to_vn_iso(get_vn_now())
        await self.col.update_one(
            {"id": hook_id},
            {
                "$set": {
                    "status": "used",
                    "updated_at": now_str,
                },
                "$inc": {"used_count": 1},
                "$push": {"used_in_videos": str(target_video_item_id)},
            },
        )
        logger.info(f"Hook [{hook_id}] đã được ghép vào video [{target_video_item_id}]")

    async def get_hook_stats(self, campaign_id: str) -> Dict[str, int]:
        """Thống kê số lượng Hook có sẵn và đã dùng trong kho."""
        available = await self.col.count_documents({"campaign_id": campaign_id, "status": "available"})
        used = await self.col.count_documents({"campaign_id": campaign_id, "status": "used"})
        return {"available": available, "used": used, "total": available + used}
