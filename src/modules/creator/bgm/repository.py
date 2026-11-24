import logging
import random
from pathlib import Path
from typing import List, Dict, Any, Optional
from bson import ObjectId
from src.core.config import settings
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso

logger = logging.getLogger("bgm_repository")

# Kho nhạc mẫu bản quyền sạch tích hợp sẵn (No-Copyright Presets - Máy chủ cục bộ)
DEFAULT_PRESET_TRACKS: List[Dict[str, Any]] = [
    {
        "title": "Lofi Chill Sunset (Bản quyền sạch)",
        "mood": "chill",
        "duration": 35.0,
        "audio_url": "/api/v1/creator/bgm/stream/preset_chill.mp3",
        "is_preset": True,
        "sanitized": True,
        "tags": ["chill", "lofi", "diy", "woodworking"],
    },
    {
        "title": "Upbeat Funk TikTok Trend (Sôi động)",
        "mood": "upbeat",
        "duration": 30.0,
        "audio_url": "/api/v1/creator/bgm/stream/preset_upbeat.mp3",
        "is_preset": True,
        "sanitized": True,
        "tags": ["upbeat", "trend", "cosplay", "fashion"],
    },
    {
        "title": "Funny Quirky Pets Comedy (Hài hước)",
        "mood": "funny",
        "duration": 25.0,
        "audio_url": "/api/v1/creator/bgm/stream/preset_funny.mp3",
        "is_preset": True,
        "sanitized": True,
        "tags": ["funny", "pets", "comedy", "cats"],
    },
    {
        "title": "Gentle Ambient ASMR Cooking (Thư giãn)",
        "mood": "asmr",
        "duration": 35.0,
        "audio_url": "/api/v1/creator/bgm/stream/preset_asmr.mp3",
        "is_preset": True,
        "sanitized": True,
        "tags": ["asmr", "cooking", "satisfying", "relax"],
    },
    {
        "title": "Epic Cinematic Inspiration (Kịch tính)",
        "mood": "cinematic",
        "duration": 35.0,
        "audio_url": "/api/v1/creator/bgm/stream/preset_cinematic.mp3",
        "is_preset": True,
        "sanitized": True,
        "tags": ["cinematic", "drama", "survival", "tech"],
    },
]


class BgmMongoRepository:
    """Repository quản lý collection bgm_tracks trong MongoDB."""

    def __init__(self, db: Optional[Any] = None):
        self.db: Any = db or get_mongo_db()
        self.col: Any = self.db["bgm_tracks"]

    @staticmethod
    def _format_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Chuẩn hóa Document MongoDB thành JSON-safe theo múi giờ Việt Nam."""
        doc["id"] = str(doc["_id"])
        doc["_id"] = str(doc["_id"])
        if "user_id" in doc and doc["user_id"]:
            doc["user_id"] = str(doc["user_id"])
        doc["created_at"] = to_vn_iso(doc.get("created_at"))
        doc["updated_at"] = to_vn_iso(doc.get("updated_at"))
        return doc

    async def seed_presets_if_needed(self) -> None:
        """Tự động đảm bảo file audio mẫu và nạp dữ liệu preset sạch vào CSDL."""
        try:
            from src.core.engines.dubbing.bgm_synthesizer import ensure_preset_audio_files
            ensure_preset_audio_files(settings.BGM_STORAGE_DIR)

            # Xóa các bản ghi mẫu cũ chứa link CDN bên ngoài (Mixkit 403)
            await self.col.delete_many({"is_preset": True, "audio_url": {"$regex": "mixkit"}})

            count = await self.col.count_documents({"is_preset": True})
            if count == 0:
                logger.info("Kho BGM chưa có dữ liệu mẫu, đang nạp preset bản quyền sạch...")
                now = get_vn_now()
                docs: List[Dict[str, Any]] = []
                for t in DEFAULT_PRESET_TRACKS:
                    url_str = str(t.get("audio_url", ""))
                    filename = Path(url_str).name
                    file_path = str(settings.BGM_STORAGE_DIR / filename)
                    doc: Dict[str, Any] = {
                        "title": str(t.get("title", "")),
                        "mood": str(t.get("mood", "chill")),
                        "duration": float(t.get("duration", 0.0)),
                        "audio_url": url_str,
                        "file_path": file_path,
                        "is_preset": True,
        "sanitized": True,
                        "tags": list(t.get("tags", [])),
                        "created_at": now,
                        "updated_at": now,
                    }
                    docs.append(doc)
                await self.col.insert_many(docs)
                logger.info(f"Đã nạp thành công {len(docs)} bài BGM preset sạch vào CSDL.")
        except Exception as e:
            logger.warning(f"Lỗi khi seed BGM presets: {e}")

    async def create_track(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo bài nhạc mới do người dùng upload."""
        now = get_vn_now()
        doc: Dict[str, Any] = {
            "user_id": data.get("user_id"),
            "title": data.get("title", "Bản nhạc mới"),
            "mood": data.get("mood", "chill"),
            "duration": float(data.get("duration", 0.0)),
            "audio_url": data.get("audio_url", ""),
            "file_path": data.get("file_path"),
            "is_preset": bool(data.get("is_preset", False)),
            "sanitized": bool(data.get("sanitized", False)),
            "tags": data.get("tags", []),
            "created_at": now,
            "updated_at": now,
        }
        res = await self.col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return self._format_doc(doc)

    async def get_tracks(
        self, user_id: Optional[str] = None, mood: Optional[str] = None, skip: int = 0, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách nhạc: Bao gồm nhạc của user + nhạc preset hệ thống."""
        query: Dict[str, Any] = {}
        if user_id:
            or_list: List[Dict[str, Any]] = [
                {"is_preset": True},
                {"user_id": user_id},
            ]
            if ObjectId.is_valid(user_id):
                or_list.append({"user_id": ObjectId(user_id)})
            query["$or"] = or_list
        else:
            query["is_preset"] = True

        if mood and mood != "all":
            query["mood"] = mood

        cursor = self.col.find(query).sort([("is_preset", -1), ("created_at", -1)]).skip(skip).limit(limit)
        items: List[Dict[str, Any]] = []
        async for doc in cursor:
            items.append(self._format_doc(doc))
        return items

    async def count_tracks(self, user_id: Optional[str] = None, mood: Optional[str] = None) -> int:
        """Đếm tổng số bài nhạc hợp lệ."""
        query: Dict[str, Any] = {}
        if user_id:
            or_list: List[Dict[str, Any]] = [
                {"is_preset": True},
                {"user_id": user_id},
            ]
            if ObjectId.is_valid(user_id):
                or_list.append({"user_id": ObjectId(user_id)})
            query["$or"] = or_list
        else:
            query["is_preset"] = True

        if mood and mood != "all":
            query["mood"] = mood
        return int(await self.col.count_documents(query))

    async def get_track_by_id(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Tìm bài nhạc theo ID."""
        if not ObjectId.is_valid(track_id):
            return None
        doc = await self.col.find_one({"_id": ObjectId(track_id)})
        return self._format_doc(doc) if doc else None

    async def get_tracks_by_ids(self, track_ids: List[str]) -> List[Dict[str, Any]]:
        """Lấy danh sách các bài nhạc theo mảng ID."""
        valid_oids = [ObjectId(tid) for tid in track_ids if ObjectId.is_valid(tid)]
        if not valid_oids:
            return []
        cursor = self.col.find({"_id": {"$in": valid_oids}})
        items: List[Dict[str, Any]] = []
        async for doc in cursor:
            items.append(self._format_doc(doc))
        return items

    async def get_random_track(
        self, user_id: Optional[str] = None, mood: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Lấy ngẫu nhiên 1 bản nhạc theo mood để tránh trùng lặp khi chạy Auto hàng loạt."""
        query: Dict[str, Any] = {}
        if user_id:
            or_list: List[Dict[str, Any]] = [
                {"is_preset": True},
                {"user_id": user_id},
            ]
            if ObjectId.is_valid(user_id):
                or_list.append({"user_id": ObjectId(user_id)})
            query["$or"] = or_list
        else:
            query["is_preset"] = True

        if mood and mood not in ["all", "random", "auto", None]:
            query["mood"] = mood

        tracks: List[Dict[str, Any]] = []
        cursor = self.col.find(query).limit(50)
        async for doc in cursor:
            tracks.append(self._format_doc(doc))

        if not tracks:
            cursor = self.col.find({}).limit(20)
            async for doc in cursor:
                tracks.append(self._format_doc(doc))

        return random.choice(tracks) if tracks else None

    async def delete_track(self, track_id: str, user_id: str) -> bool:
        """Xóa bài nhạc do user tự thêm (Không cho xóa preset hệ thống)."""
        if not ObjectId.is_valid(track_id):
            return False
        user_matches: List[Any] = [user_id]
        if ObjectId.is_valid(user_id):
            user_matches.append(ObjectId(user_id))
        res = await self.col.delete_one({
            "_id": ObjectId(track_id),
            "is_preset": False,
            "user_id": {"$in": user_matches},
        })
        return bool(res.deleted_count > 0)
