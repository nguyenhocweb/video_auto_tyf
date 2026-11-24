"""Repository thao tác với CSDL MongoDB cho Mẫu Video CapCut (Collection: capcut_templates).
Tuân thủ nghiêm ngặt chuẩn kiến trúc Python Backend và múi giờ Việt Nam (UTC+7).
"""

import logging
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso

logger = logging.getLogger("template_video_repository")


class TemplateVideoRepository:
    """Repository quản lý CRUD mẫu video CapCut trong MongoDB."""

    COLLECTION_NAME = "capcut_templates"

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self.db = db or get_mongo_db()
        self.collection = self.db[self.COLLECTION_NAME]

    def _format_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Chuẩn hóa ObjectId MongoDB sang chuỗi id."""
        if not doc:
            return {}
        result = dict(doc)
        if "_id" in result:
            result["id"] = str(result.pop("_id"))
        return result

    async def save_template(self, user_id: str, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu hoặc cập nhật (upsert) mẫu CapCut vào CSDL MongoDB."""
        tpl_id = str(template_data.get("template_id", "")).strip()
        if not tpl_id:
            raise ValueError("Template ID không được để trống!")

        now_iso = to_vn_iso(get_vn_now())
        existing = await self.collection.find_one({"template_id": tpl_id})

        doc_payload = {
            "template_id": tpl_id,
            "title": template_data.get("title", f"Mẫu CapCut {tpl_id}"),
            "author_name": template_data.get("author_name", "CapCut Creator"),
            "total_duration": float(template_data.get("total_duration", 0)),
            "total_slots": int(template_data.get("total_slots", 0)),
            "image_slots_count": int(template_data.get("image_slots_count", 0)),
            "video_slots_count": int(template_data.get("video_slots_count", 0)),
            "slots": template_data.get("slots", []),
            "cover_url": template_data.get("cover_url"),
            "video_url": template_data.get("video_url"),
            "music_title": template_data.get("music_title"),
            "music_url": template_data.get("music_url"),
            "source_url": template_data.get("source_url", ""),
            "updated_at": now_iso,
            "user_id": user_id,
        }

        if existing:
            doc_payload["created_at"] = existing.get("created_at", now_iso)
            await self.collection.update_one({"template_id": tpl_id}, {"$set": doc_payload})
            updated_doc = await self.collection.find_one({"template_id": tpl_id})
            logger.info(f"Đã cập nhật mẫu CapCut ID {tpl_id} trong MongoDB")
            return self._format_doc(updated_doc or doc_payload)
        else:
            doc_payload["created_at"] = now_iso
            res = await self.collection.insert_one(doc_payload)
            doc_payload["id"] = str(res.inserted_id)
            logger.info(f"Đã thêm mới mẫu CapCut ID {tpl_id} vào MongoDB")
            return doc_payload

    async def list_templates(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách tất cả các mẫu CapCut đã lưu trong MongoDB."""
        query: Dict[str, Any] = {}
        cursor = self.collection.find(query).sort("updated_at", -1)
        docs = await cursor.to_list(length=100)
        return [self._format_doc(d) for d in docs]

    async def get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Tìm chi tiết 1 mẫu CapCut theo template_id."""
        doc = await self.collection.find_one({"template_id": template_id})
        return self._format_doc(doc) if doc else None

    async def delete_template(self, template_id: str, user_id: Optional[str] = None) -> bool:
        """Xóa một mẫu CapCut khỏi CSDL MongoDB."""
        query = {"template_id": template_id}
        res = await self.collection.delete_one(query)
        logger.info(f"Xóa mẫu CapCut {template_id} từ MongoDB, deleted_count={res.deleted_count}")
        return res.deleted_count > 0

    async def is_template_saved(self, template_id: str) -> bool:
        """Kiểm tra mẫu đã được lưu trong CSDL chưa."""
        count = await self.collection.count_documents({"template_id": template_id})
        return count > 0
