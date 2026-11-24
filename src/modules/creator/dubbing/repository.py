import datetime
import logging
from typing import List, Dict, Any, Optional
from bson import ObjectId
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso

logger = logging.getLogger("dubbing_repository")


class DubbingMongoRepository:
    """Repository quản lý collection dubbing_tasks trong MongoDB."""

    def __init__(self, db: Optional[Any] = None):
        self.db: Any = db or get_mongo_db()
        self.col: Any = self.db["dubbing_tasks"]

    async def create_job(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Tạo một tác vụ xử lý Vietsub / Dubbing mới."""
        now = get_vn_now()
        # Xác định tên giọng đọc hiển thị thân thiện
        voice_source = data.get("voice_source", "preset")
        voice_preset = data.get("voice_preset", "vi-VN-NamMinhNeural")
        voice_profile_id = data.get("voice_profile_id")
        voice_name = data.get("voice_name")

        if not voice_name or (voice_source == "profile" and ("Nam Minh" in str(voice_name) or "Hoài My" in str(voice_name))):
            if voice_source == "profile" or voice_profile_id:
                pid = str(voice_profile_id) if voice_profile_id else "AI"
                voice_name = f"Giọng Cá Nhân (#{pid[-4:] if len(pid) >= 4 else pid})"
            elif "HoaiMy" in str(voice_preset):
                voice_name = "Hoài My (Nữ Truyền Cảm)"
            else:
                voice_name = "Nam Minh (Nam Trầm Ấm)"

        doc: Dict[str, Any] = {
            "user_id": data.get("user_id"),
            "video_url": data.get("video_url"),
            "source_url": data.get("source_url") or data.get("video_url"),
            "title": data.get("title", "Video Douyin AI"),
            "cover_url": data.get("cover_url"),
            "mode": data.get("mode", "both"),
            "voice_source": data.get("voice_source", "preset"),
            "voice_preset": voice_preset,
            "voice_profile_id": data.get("voice_profile_id"),
            "voice_name": voice_name,
            "remove_subtitles": data.get("remove_subtitles", True),
            "bgm_volume": data.get("bgm_volume", 0.18),
            "voice_volume": data.get("voice_volume", 1.0),
            "status": data.get("status", "pending"),
            "progress_step": data.get("progress_step", "Đang chờ vào hàng đợi..."),
            "progress_percent": data.get("progress_percent", 0),
            "segments_count": len(data.get("segments", [])),
            "output_video_url": None,
            "cloudinary_url": None,
            "subtitle_srt_url": None,
            "subtitle_ass_url": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        res = await self.col.insert_one(doc)
        doc["_id"] = str(res.inserted_id)
        return self._format_doc(doc)

    async def update_progress(
        self,
        job_id: str,
        status: str,
        progress_step: str,
        progress_percent: int,
        title: Optional[str] = None,
        cover_url: Optional[str] = None,
        output_video_url: Optional[str] = None,
        cloudinary_url: Optional[str] = None,
        subtitle_srt_url: Optional[str] = None,
        subtitle_ass_url: Optional[str] = None,
        error_message: Optional[str] = None,
        segments_count: Optional[int] = None,
        segments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Cập nhật tiến trình chi tiết của tác vụ chạy ngầm."""
        now = get_vn_now()
        update_data: Dict[str, Any] = {
            "status": status,
            "progress_step": progress_step,
            "progress_percent": progress_percent,
            "updated_at": now,
        }
        if title is not None:
            update_data["title"] = title
        if cover_url is not None:
            update_data["cover_url"] = cover_url
        if output_video_url is not None:
            update_data["output_video_url"] = output_video_url
        if cloudinary_url is not None:
            update_data["cloudinary_url"] = cloudinary_url
        if subtitle_srt_url is not None:
            update_data["subtitle_srt_url"] = subtitle_srt_url
        if subtitle_ass_url is not None:
            update_data["subtitle_ass_url"] = subtitle_ass_url
        if error_message is not None:
            update_data["error_message"] = error_message
        if segments_count is not None:
            update_data["segments_count"] = segments_count
        if segments is not None:
            update_data["segments"] = segments

        query_id = ObjectId(job_id) if ObjectId.is_valid(job_id) else job_id
        res = await self.col.update_one({"_id": query_id}, {"$set": update_data})
        return res.modified_count > 0

    @staticmethod
    def _format_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Chuẩn hóa dữ liệu Document MongoDB thành JSON-safe theo múi giờ Việt Nam (+07:00)."""
        doc["id"] = str(doc["_id"])
        doc["_id"] = str(doc["_id"])
        doc["user_id"] = str(doc.get("user_id", ""))
        doc["created_at"] = to_vn_iso(doc.get("created_at"))
        doc["updated_at"] = to_vn_iso(doc.get("updated_at"))
        is_profile = doc.get("voice_source") == "profile" or bool(doc.get("voice_profile_id"))
        current_name = doc.get("voice_name")
        if not current_name or (is_profile and ("Nam Minh" in str(current_name) or "Hoài My" in str(current_name))):
            if is_profile:
                pid = str(doc.get("voice_profile_id") or "AI")
                doc["voice_name"] = f"Giọng Cá Nhân (#{pid[-4:] if len(pid) >= 4 else pid})"
            elif "HoaiMy" in str(doc.get("voice_preset", "")):
                doc["voice_name"] = "Hoài My (Nữ Truyền Cảm)"
            else:
                doc["voice_name"] = "Nam Minh (Nam Trầm Ấm)"
        return doc

    async def get_job_by_id(self, job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chi tiết của tác vụ (bảo mật nghiêm ngặt theo user_id)."""
        query_id = ObjectId(job_id) if ObjectId.is_valid(job_id) else job_id
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        doc = await self.col.find_one({"_id": query_id, **user_q})
        return self._format_doc(doc) if doc else None

    async def get_user_jobs(
        self, user_id: str, skip: int = 0, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách các tác vụ dubbing của người dùng có phân trang (chỉ thấy của chính mình)."""
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        cursor = (
            self.col.find(user_q)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [self._format_doc(doc) async for doc in cursor]

    async def count_user_jobs(self, user_id: str) -> int:
        """Đếm tổng số tác vụ của riêng người dùng."""
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        return await self.col.count_documents(user_q)

    async def delete_job(self, job_id: str, user_id: str) -> bool:
        """Xóa tác vụ dubbing (chỉ người tạo mới được quyền xóa)."""
        query_id = ObjectId(job_id) if ObjectId.is_valid(job_id) else job_id
        user_q = (
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]}
            if ObjectId.is_valid(user_id)
            else {"user_id": user_id}
        )
        res = await self.col.delete_one({"_id": query_id, **user_q})
        return res.deleted_count > 0

    async def cleanup_stale_processing_jobs(self, timeout_minutes: int = 45) -> int:
        """Chỉ dọn dẹp các tác vụ processing mồ côi thực sự (không có cập nhật > timeout_minutes)."""
        now = get_vn_now()
        threshold_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(minutes=timeout_minutes)
        res = await self.col.update_many(
            {
                "status": {"$in": ["processing", "pending"]},
                "$or": [
                    {"updated_at": {"$lt": threshold_utc}},
                    {"updated_at": None, "created_at": {"$lt": threshold_utc}},
                ],
            },
            {
                "$set": {
                    "status": "failed",
                    "progress_step": "Bị gián đoạn do tắt máy hoặc server khởi động lại. Vui lòng bấm Thử Lại.",
                    "error_message": f"Tác vụ bị gián đoạn (không phản hồi > {timeout_minutes} phút).",
                    "updated_at": now,
                }
            },
        )
        if res.modified_count > 0:
            logger.info(f"Đã dọn dẹp {res.modified_count} tác vụ mồ côi (stale processing/pending > {timeout_minutes}p).")
        return res.modified_count
