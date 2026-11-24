import datetime
import logging
from typing import List, Dict, Any, Optional
from bson import ObjectId
from src.core.database_mongo import get_mongo_db

logger = logging.getLogger("audio_generation_repository")


class AudioGenerationMongoRepository:
    """Repository quản lý riêng biệt bảng AudioGeneration (Lịch sử các bản thu âm)."""

    def __init__(self, db: Optional[Any] = None):
        self.db: Any = db or get_mongo_db()
        self.col: Any = self.db["audio_generations"]

    async def create_generation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo bản ghi yêu cầu sinh âm thanh ở trạng thái PENDING."""
        now = datetime.datetime.now(datetime.timezone.utc)
        doc = {
            "user_id": data.get("user_id"),
            "generation_type": data.get("generation_type", "SYNTHESIZE"),
            "voice_profile_id": data.get("voice_profile_id"),
            "voice_name": data.get("voice_name", "Giọng AI"),
            "input_text": data["input_text"],
            "instruct_prompt": data.get("instruct_prompt"),
            "speed": data.get("speed", 1.0),
            "num_step": data.get("num_step", 28),
            "guidance_scale": data.get("guidance_scale", 2.0),
            "status": data.get("status", "PENDING"),
            "cloudinary_audio": None,
            "process_time_seconds": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        res = await self.col.insert_one(doc)
        doc["_id"] = str(res.inserted_id)
        doc["id"] = str(res.inserted_id)
        return doc

    async def update_generation(self, generation_id: str, updates: Dict[str, Any]) -> bool:
        """Cập nhật tiến trình, trạng thái hoặc kết quả sinh âm thanh."""
        try:
            query = {"_id": ObjectId(generation_id)} if ObjectId.is_valid(generation_id) else {"_id": generation_id}
            updates["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
            res = await self.col.update_one(query, {"$set": updates})
            return res.modified_count > 0
        except Exception as exc:
            logger.error(f"update_generation error: {exc}")
            return False

    async def get_by_id(self, generation_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết một bản ghi thu âm."""
        try:
            query = {"_id": ObjectId(generation_id)} if ObjectId.is_valid(generation_id) else {"_id": generation_id}
            doc = await self.col.find_one(query)
            if doc:
                doc["id"] = str(doc["_id"])
            return doc
        except Exception as exc:
            logger.error(f"get_by_id error: {exc}")
            return None

    async def list_user_recordings(
        self,
        user_id: Optional[str] = None,
        is_admin: bool = False,
        skip: int = 0,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách bản thu âm. Phân quyền: User chỉ xem của mình, Admin xem tất cả."""
        try:
            filter_query: Dict[str, Any] = {}
            if not is_admin and user_id:
                filter_query["user_id"] = user_id

            cursor = self.col.find(filter_query).sort("created_at", -1).skip(skip).limit(limit)
            items = []
            async for doc in cursor:
                doc["id"] = str(doc["_id"])
                items.append(doc)
            return items
        except Exception as exc:
            logger.error(f"list_user_recordings error: {exc}")
            return []

    async def count_recordings(self, user_id: Optional[str] = None, is_admin: bool = False) -> int:
        """Đếm tổng số bản thu âm theo phân quyền."""
        try:
            filter_query: Dict[str, Any] = {}
            if not is_admin and user_id:
                filter_query["user_id"] = user_id
            return await self.col.count_documents(filter_query)
        except Exception:
            return 0

    async def delete_recording(self, generation_id: str, user_id: str, is_admin: bool = False) -> bool:
        """Xóa bản thu âm. User chỉ được xóa của mình, Admin xóa bất kỳ."""
        try:
            query: Dict[str, Any] = {"_id": ObjectId(generation_id)} if ObjectId.is_valid(generation_id) else {"_id": generation_id}
            if not is_admin:
                query["user_id"] = user_id

            res = await self.col.delete_one(query)
            return res.deleted_count > 0
        except Exception as exc:
            logger.error(f"delete_recording error: {exc}")
            return False

