import datetime
import logging
from typing import List, Dict, Any, Optional
from bson import ObjectId
from src.core.database_mongo import get_mongo_db

logger = logging.getLogger("voice_mongo_repository")


class VoiceMongoRepository:
    """
    Tầng Repository tương tác trực tiếp với MongoDB.
    Chỉ quản lý các bảng phục vụ Training & Sinh Giọng Nói (Voice Training & TTS Collections).
    Không chứa bảng User theo đúng yêu cầu người dùng.
    """

    def __init__(self, db: Optional[Any] = None):
        self.db: Any = db or get_mongo_db()
        self.samples_col: Any = self.db["voice_samples"]
        self.profiles_col: Any = self.db["voice_profiles"]
        self.generations_col: Any = self.db["audio_generations"]
        self.training_jobs_col: Any = self.db["voice_training_jobs"]
        self.training_samples_col: Any = self.db["voice_training_samples"]

    # =========================================================================
    # 1. VOICE SAMPLES (File mẫu âm thanh 3-10s)
    # =========================================================================
    async def find_sample_by_hash(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Kiểm tra mã băm SHA-256 để chống upload trùng lặp lên Cloudinary."""
        try:
            doc = await self.samples_col.find_one({"file_hash": file_hash})
            if doc:
                doc["_id"] = str(doc["_id"])
            return doc
        except Exception as exc:
            logger.warning(f"find_sample_by_hash error: {exc}")
            return None

    async def create_voice_sample(self, sample_data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu thông tin mẫu âm thanh đã tải lên Cloudinary."""
        now = datetime.datetime.now(datetime.timezone.utc)
        doc = {
            "original_filename": sample_data["original_filename"],
            "file_hash": sample_data["file_hash"],
            "duration_seconds": sample_data["duration_seconds"],
            "sample_rate": sample_data.get("sample_rate", 24000),
            "channels": sample_data.get("channels", 1),
            "format": sample_data.get("format", "wav"),
            "size_bytes": sample_data.get("size_bytes", 0),
            "cloudinary": sample_data["cloudinary"],
            "whisper_transcript": sample_data.get("whisper_transcript"),
            "waveform_peaks": sample_data.get("waveform_peaks", []),
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
        }
        try:
            res = await self.samples_col.insert_one(doc)
            doc["_id"] = str(res.inserted_id)
        except Exception as exc:
            logger.warning(f"create_voice_sample error: {exc}")
            doc["_id"] = f"fallback_{sample_data['file_hash'][:8]}"
        return doc

    async def get_voice_sample(self, sample_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết file audio mẫu từ MongoDB."""
        try:
            query = {"_id": ObjectId(sample_id)} if ObjectId.is_valid(sample_id) else {"_id": sample_id}
            doc = await self.samples_col.find_one(query)
            if doc:
                doc["_id"] = str(doc["_id"])
            return doc
        except Exception as exc:
            logger.warning(f"get_voice_sample error: {exc}")
            return None

    # =========================================================================
    # 2. VOICE PROFILES (Hồ sơ kiểu giọng đã training/trích xuất embedding)
    # =========================================================================
    async def create_voice_profile(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu hồ sơ kiểu giọng đã training và trích xuất embedding .pt."""
        now = datetime.datetime.now(datetime.timezone.utc)
        custom_id = profile_data.get("profile_id") or profile_data.get("_id")
        doc = {
            "user_id": profile_data.get("user_id"),
            "profile_name": profile_data["profile_name"],
            "description": profile_data.get("description", ""),
            "gender": profile_data.get("gender", "NEUTRAL"),
            "language": profile_data.get("language", "vi"),
            "tags": profile_data.get("tags", []),
            "cloudinary_embedding": profile_data["cloudinary_embedding"],
            "source_sample_id": profile_data.get("source_sample_id"),
            "is_preset": profile_data.get("is_preset", False),
            "usage_count": 0,
            "status": "ACTIVE",
            "created_at": now,
            "updated_at": now,
        }
        if custom_id:
            doc["_id"] = str(custom_id)

        try:
            res = await self.profiles_col.insert_one(doc)
            doc["_id"] = str(res.inserted_id)
        except Exception as exc:
            logger.warning(f"create_voice_profile error: {exc}")
            doc["_id"] = str(custom_id or f"local_{profile_data['profile_name'][:8]}")
        return doc

    async def list_voice_profiles(
        self, limit: int = 50, user_id: Optional[str] = None, is_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách các hồ sơ giọng đã lưu. Phân quyền: User chỉ thấy giọng của mình & preset, Admin thấy tất cả."""
        try:
            filter_query: Dict[str, Any] = {"status": "ACTIVE"}
            if not is_admin and user_id:
                filter_query["$or"] = [
                    {"is_preset": True},
                    {"user_id": user_id},
                    {"user_id": None},
                ]

            cursor = self.profiles_col.find(filter_query).sort([
                ("is_preset", -1),
                ("created_at", -1)
            ]).limit(limit)

            profiles = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                profiles.append(doc)
            return profiles
        except Exception as exc:
            logger.warning(f"list_voice_profiles error: {exc}")
            return []

    async def get_voice_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết hồ sơ giọng để tải file .pt vào bộ nhớ AI."""
        try:
            query = {"_id": ObjectId(profile_id)} if ObjectId.is_valid(profile_id) else {"_id": profile_id}
            doc = await self.profiles_col.find_one(query)
            if doc:
                doc["_id"] = str(doc["_id"])
            return doc
        except Exception as exc:
            logger.warning(f"get_voice_profile_by_id error: {exc}")
            return None

    async def increment_profile_usage(self, profile_id: str):
        """Tăng số lượt sử dụng khi đọc kịch bản."""
        try:
            query = {"_id": ObjectId(profile_id)} if ObjectId.is_valid(profile_id) else {"_id": profile_id}
            await self.profiles_col.update_one(query, {"$inc": {"usage_count": 1}})
        except Exception as exc:
            logger.warning(f"increment_profile_usage error: {exc}")

    async def delete_voice_profile(self, profile_id: str) -> bool:
        """Xóa hồ sơ giọng nói."""
        try:
            query = {"_id": ObjectId(profile_id)} if ObjectId.is_valid(profile_id) else {"_id": profile_id}
            res = await self.profiles_col.delete_one(query)
            return res.deleted_count > 0
        except Exception as exc:
            logger.warning(f"delete_voice_profile error: {exc}")
            return False

    # =========================================================================
    # 3. AUDIO GENERATIONS (Lịch sử các lần tạo âm thanh thuyết minh)
    # =========================================================================
    async def create_audio_generation(self, gen_data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo bản ghi phiên sinh âm thanh (lưu kịch bản và thông số)."""
        now = datetime.datetime.now(datetime.timezone.utc)
        doc = {
            "generation_type": gen_data.get("generation_type", "CLONE"),
            "voice_profile_id": gen_data.get("voice_profile_id"),
            "source_sample_id": gen_data.get("source_sample_id"),
            "input_text": gen_data["input_text"],
            "instruct_prompt": gen_data.get("instruct_prompt"),
            "speed": gen_data.get("speed", 1.0),
            "num_step": gen_data.get("num_step", 28),
            "guidance_scale": gen_data.get("guidance_scale", 2.0),
            "status": gen_data.get("status", "COMPLETED"),
            "cloudinary_audio": gen_data.get("cloudinary_audio"),
            "process_time_seconds": gen_data.get("process_time_seconds"),
            "error_message": gen_data.get("error_message"),
            "created_at": now,
            "updated_at": now,
        }
        try:
            res = await self.generations_col.insert_one(doc)
            doc["_id"] = str(res.inserted_id)
        except Exception as exc:
            logger.warning(f"create_audio_generation error: {exc}")
            doc["_id"] = "fallback_gen"
        return doc

    async def list_recent_generations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Lấy danh sách các file audio vừa tạo gần đây."""
        try:
            cursor = self.generations_col.find({"status": "COMPLETED"}).sort("created_at", -1).limit(limit)
            items = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                items.append(doc)
            return items
        except Exception as exc:
            logger.warning(f"list_recent_generations error: {exc}")
            return []

    # =========================================================================
    # 4. VOICE TRAINING JOBS (Quản lý tiến trình huấn luyện chuyên sâu 99%)
    # =========================================================================
    async def create_training_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        import uuid
        now = datetime.datetime.now(datetime.timezone.utc)
        doc = {
            "user_id": job_data.get("user_id"),
            "voice_name": job_data["voice_name"],
            "gender": job_data.get("gender", "NEUTRAL"),
            "status": "RECORDING",
            "total_samples": 0,
            "total_duration_seconds": 0.0,
            "target_epochs": job_data.get("target_epochs", 20),
            "current_epoch": 0,
            "current_loss": None,
            "progress_percent": 0,
            "estimated_remaining_sec": None,
            "device_used": job_data.get("device_used", "cuda:0"),
            "cloudinary_model_url": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        try:
            res = await self.training_jobs_col.insert_one(doc)
            doc["_id"] = str(res.inserted_id)
        except Exception as exc:
            logger.warning(f"create_training_job error: {exc}")
            doc["_id"] = f"job_local_{uuid.uuid4().hex[:8]}"
        return doc

    async def get_training_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            query = {"_id": ObjectId(job_id)} if ObjectId.is_valid(job_id) else {"_id": job_id}
            doc = await self.training_jobs_col.find_one(query)
            if doc:
                doc["_id"] = str(doc["_id"])
            return doc
        except Exception as exc:
            logger.warning(f"get_training_job error: {exc}")
            return None

    async def update_training_job(self, job_id: str, update_data: Dict[str, Any]):
        try:
            query = {"_id": ObjectId(job_id)} if ObjectId.is_valid(job_id) else {"_id": job_id}
            update_data["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
            await self.training_jobs_col.update_one(query, {"$set": update_data})
        except Exception as exc:
            logger.warning(f"update_training_job error: {exc}")

    async def save_training_sample(self, sample_data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.datetime.now(datetime.timezone.utc)
        doc = {
            "job_id": sample_data["job_id"],
            "prompt_id": sample_data["prompt_id"],
            "prompt_text": sample_data["prompt_text"],
            "duration_seconds": sample_data.get("duration_seconds", 0.0),
            "cloudinary_url": sample_data["cloudinary_url"],
            "public_id": sample_data.get("public_id"),
            "file_size": sample_data.get("file_size", 0),
            "created_at": now,
        }
        try:
            res = await self.training_samples_col.insert_one(doc)
            doc["_id"] = str(res.inserted_id)
            query = {"_id": ObjectId(sample_data["job_id"])} if ObjectId.is_valid(sample_data["job_id"]) else {"_id": sample_data["job_id"]}
            await self.training_jobs_col.update_one(query, {
                "$inc": {
                    "total_samples": 1,
                    "total_duration_seconds": sample_data.get("duration_seconds", 0.0),
                }
            })
        except Exception as exc:
            logger.warning(f"save_training_sample error: {exc}")
            doc["_id"] = "sample_local"
        return doc

    async def get_training_samples_by_job(self, job_id: str) -> List[Dict[str, Any]]:
        try:
            cursor = self.training_samples_col.find({"job_id": job_id}).sort("prompt_id", 1)
            items = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                items.append(doc)
            return items
        except Exception as exc:
            logger.warning(f"get_training_samples_by_job error: {exc}")
            return []
