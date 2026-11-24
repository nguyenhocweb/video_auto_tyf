import uuid
import logging
from typing import List, Dict, Any, Optional
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso

logger = logging.getLogger("groq_keys_repository")


class GroqKeysMongoRepository:
    """Repository quản lý lưu trữ danh sách Groq API Keys trên MongoDB riêng biệt."""

    @classmethod
    def mask_key(cls, key: str) -> str:
        """Che giấu một phần API Key để hiển thị an toàn trên giao diện."""
        s = key.strip()
        if len(s) <= 10:
            return s[:3] + "..." + s[-3:]
        return s[:7] + "..." + s[-4:]

    async def get_all_keys(self) -> List[Dict[str, Any]]:
        """Lấy danh sách toàn bộ các Key kèm thông tin thống kê."""
        db = get_mongo_db()
        cursor = db.groq_api_keys.find({}).sort("created_at", -1)
        items = []
        async for doc in cursor:
            items.append({
                "id": str(doc.get("id")),
                "key_masked": self.mask_key(doc.get("key", "")),
                "note": doc.get("note", ""),
                "model": doc.get("model", "qwen/qwen3.8-27b"),
                "is_active": doc.get("is_active", True),
                "usage_count": doc.get("usage_count", 0),
                "error_count": doc.get("error_count", 0),
                "last_used_at": doc.get("last_used_at"),
                "created_at": doc.get("created_at", ""),
            })
        return items

    async def get_active_keys(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các Key đang bật (is_active=True) để xoay tua dịch thuật."""
        db = get_mongo_db()
        cursor = db.groq_api_keys.find({"is_active": True})
        active_keys = []
        async for doc in cursor:
            active_keys.append({
                "id": str(doc.get("id")),
                "key": doc.get("key", "").strip(),
                "note": doc.get("note", ""),
                "model": doc.get("model", "qwen/qwen3.8-27b"),
            })
        return active_keys

    async def get_key_raw(self, key_id: str) -> Optional[str]:
        """Lấy giá trị nguyên bản của key để thực hiện kiểm tra kết nối API."""
        db = get_mongo_db()
        doc = await db.groq_api_keys.find_one({"id": str(key_id)})
        return doc.get("key", "").strip() if doc else None

    async def add_key(
        self, user_id: str, key: str, note: str = "", model: str = "qwen/qwen3.8-27b"
    ) -> Dict[str, Any]:
        """Thêm một API Key mới vào Database."""
        db = get_mongo_db()
        clean_key = key.strip()
        clean_model = model.strip() if model else "qwen/qwen3.8-27b"
        now_iso = to_vn_iso(get_vn_now())
        key_id = f"groq_{uuid.uuid4().hex[:12]}"

        existing = await db.groq_api_keys.find_one({"key": clean_key})
        if existing:
            raise ValueError("API Key này đã tồn tại trong kho Groq.")

        doc = {
            "id": key_id,
            "user_id": user_id,
            "key": clean_key,
            "note": note.strip() or "Khóa Groq Cloud",
            "model": clean_model,
            "is_active": True,
            "usage_count": 0,
            "error_count": 0,
            "last_used_at": None,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        await db.groq_api_keys.insert_one(doc)
        logger.info(f"Đã thêm Groq Key [{self.mask_key(clean_key)}] model [{clean_model}] vào DB.")
        return {
            "id": key_id,
            "key_masked": self.mask_key(clean_key),
            "note": doc["note"],
            "model": clean_model,
            "is_active": True,
            "usage_count": 0,
            "error_count": 0,
            "last_used_at": None,
            "created_at": now_iso,
        }

    async def update_key_model(self, key_id: str, model: str) -> Optional[Dict[str, Any]]:
        """Cập nhật Model Groq được chỉ định cho Key."""
        db = get_mongo_db()
        clean_model = model.strip() if model else "qwen/qwen3.8-27b"
        now_iso = to_vn_iso(get_vn_now())
        res = await db.groq_api_keys.find_one_and_update(
            {"id": str(key_id)},
            {"$set": {"model": clean_model, "updated_at": now_iso}},
            return_document=True,
        )
        if not res:
            return None
        return {
            "id": str(res.get("id")),
            "key_masked": self.mask_key(res.get("key", "")),
            "note": res.get("note", ""),
            "model": res.get("model", clean_model),
            "is_active": res.get("is_active", True),
            "usage_count": res.get("usage_count", 0),
            "error_count": res.get("error_count", 0),
            "last_used_at": res.get("last_used_at"),
            "created_at": res.get("created_at", ""),
        }

    async def delete_key(self, key_id: str) -> bool:
        """Xóa một API Key khỏi Database."""
        db = get_mongo_db()
        res = await db.groq_api_keys.delete_one({"id": str(key_id)})
        return res.deleted_count > 0

    async def toggle_key(self, key_id: str) -> Optional[bool]:
        """Bật hoặc tắt trạng thái hoạt động của một API Key."""
        db = get_mongo_db()
        doc = await db.groq_api_keys.find_one({"id": str(key_id)})
        if not doc:
            return None
        new_status = not doc.get("is_active", True)
        now_iso = to_vn_iso(get_vn_now())
        await db.groq_api_keys.update_one(
            {"id": str(key_id)},
            {"$set": {"is_active": new_status, "updated_at": now_iso}},
        )
        return new_status

    async def record_usage(self, key_id: str, success: bool) -> None:
        """Ghi nhận lượt gọi thành công hoặc gặp lỗi của Key."""
        try:
            db = get_mongo_db()
            now_iso = to_vn_iso(get_vn_now())
            inc_field = "usage_count" if success else "error_count"
            await db.groq_api_keys.update_one(
                {"id": str(key_id)},
                {
                    "$inc": {inc_field: 1},
                    "$set": {"last_used_at": now_iso, "updated_at": now_iso},
                },
            )
        except Exception as e:
            logger.debug(f"Không thể cập nhật thống kê Groq key {key_id}: {e}")

