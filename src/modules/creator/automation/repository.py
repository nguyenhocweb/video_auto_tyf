import datetime
from bson import ObjectId
from typing import List, Dict, Any, Optional
from src.core.database_mongo import get_mongo_db
from src.core.utils.date_utils import get_vn_now, to_vn_iso


class AutomationMongoRepository:
    def __init__(self):
        self.db = get_mongo_db()
        self.campaigns_col = self.db["automation_campaigns"]
        self.logs_col = self.db["automation_logs"]
        self.posted_videos_col = self.db["automation_posted_videos"]

    @staticmethod
    def _doc_to_dict(doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return {}
        res = dict(doc)
        if "_id" in res:
            res["id"] = str(res["_id"])
            del res["_id"]
        for k in ["created_at", "updated_at", "last_run_at", "next_run_at", "crawled_at", "posted_at"]:
            if k in res and res[k]:
                res[k] = to_vn_iso(res[k])
        return res

    async def create_campaign(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        now = to_vn_iso(get_vn_now())
        next_run = now  # Kích hoạt chạy ngay lần đầu tiên
        doc = {
            **data,
            "user_id": str(user_id),
            "status": "idle",
            "total_posted": 0,
            "last_run_at": None,
            "next_run_at": next_run,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }
        res = await self.campaigns_col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return self._doc_to_dict(doc)

    async def get_user_campaigns(self, user_id: str) -> List[Dict[str, Any]]:
        cursor = self.campaigns_col.find({"user_id": str(user_id)}).sort("created_at", -1)
        items = []
        async for doc in cursor:
            items.append(self._doc_to_dict(doc))
        return items

    async def get_campaign_by_id(
        self, campaign_id: str, user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        query: Dict[str, Any] = {"_id": ObjectId(campaign_id)}
        if user_id:
            query["user_id"] = str(user_id)
        doc = await self.campaigns_col.find_one(query)
        return self._doc_to_dict(doc) if doc else None

    async def update_campaign(
        self, campaign_id: str, user_id: str, update_dict: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        update_dict["updated_at"] = to_vn_iso(get_vn_now())
        res = await self.campaigns_col.find_one_and_update(
            {"_id": ObjectId(campaign_id), "user_id": str(user_id)},
            {"$set": update_dict},
            return_document=True,
        )
        return self._doc_to_dict(res) if res else None

    async def delete_campaign(self, campaign_id: str, user_id: str) -> bool:
        res = await self.campaigns_col.delete_one(
            {"_id": ObjectId(campaign_id), "user_id": str(user_id)}
        )
        return res.deleted_count > 0

    async def toggle_active(
        self, campaign_id: str, user_id: str, is_active: bool
    ) -> Optional[Dict[str, Any]]:
        now = to_vn_iso(get_vn_now())
        update_data: Dict[str, Any] = {
            "is_active": is_active,
            "status": "idle" if is_active else "paused",
            "updated_at": now,
        }
        if is_active:
            update_data["next_run_at"] = now
        res = await self.campaigns_col.find_one_and_update(
            {"_id": ObjectId(campaign_id), "user_id": str(user_id)},
            {"$set": update_data},
            return_document=True,
        )
        return self._doc_to_dict(res) if res else None

    async def acquire_campaign_lock(self, campaign_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Khóa nguyên tử (Atomic Lock) chống chạy trùng chu kỳ cho chiến dịch."""
        now = to_vn_iso(get_vn_now())
        res = await self.campaigns_col.find_one_and_update(
            {"_id": ObjectId(campaign_id), "user_id": str(user_id), "status": {"$ne": "running"}},
            {"$set": {"status": "running", "updated_at": now}},
            return_document=True,
        )
        return self._doc_to_dict(res) if res else None

    async def get_due_campaigns(self) -> List[Dict[str, Any]]:
        """Lấy các chiến dịch đang bật (is_active == True) và đã đến thời điểm chạy next_run_at."""
        now = to_vn_iso(get_vn_now())
        query = {
            "is_active": True,
            "status": {"$ne": "running"},
            "$or": [
                {"next_run_at": {"$lte": now}},
                {"next_run_at": None},
                {"next_run_at": {"$exists": False}},
            ],
        }
        cursor = self.campaigns_col.find(query)
        items = []
        async for doc in cursor:
            items.append(self._doc_to_dict(doc))
        return items

    async def recover_stuck_campaigns(self, timeout_minutes: int = 10) -> int:
        """Tự động giải phóng các chiến dịch bị kẹt trạng thái 'running' quá 10 phút."""
        cutoff = to_vn_iso(get_vn_now() - datetime.timedelta(minutes=timeout_minutes))
        res = await self.campaigns_col.update_many(
            {
                "status": "running",
                "$or": [
                    {"updated_at": {"$lte": cutoff}},
                    {"updated_at": None},
                    {"updated_at": {"$exists": False}},
                ],
            },
            {"$set": {"status": "idle", "updated_at": to_vn_iso(get_vn_now())}},
        )

        # Tự động giải phóng các video bị kẹt trạng thái 'processing' quá 25 phút
        proc_cutoff = to_vn_iso(get_vn_now() - datetime.timedelta(minutes=25))
        await self.logs_col.update_many(
            {
                "status": "processing",
                "created_at": {"$lte": proc_cutoff},
            },
            {"$set": {"status": "failed", "details": "Đã giải phóng do quá thời gian xử lý (Timeout)"}},
        )
        return res.modified_count

    async def update_campaign_run_state(
        self,
        campaign_id: str,
        status: str,
        last_run_at: Optional[str] = None,
        next_run_at: Optional[str] = None,
        increment_posted: int = 0,
        error: Optional[str] = None,
    ) -> None:
        update_set: Dict[str, Any] = {
            "status": status,
            "updated_at": to_vn_iso(get_vn_now()),
        }
        if last_run_at:
            update_set["last_run_at"] = last_run_at
        if next_run_at:
            update_set["next_run_at"] = next_run_at
        if error is not None:
            update_set["last_error"] = error
        else:
            update_set["last_error"] = None

        update_ops: Dict[str, Any] = {"$set": update_set}
        if increment_posted > 0:
            update_ops["$inc"] = {"total_posted": increment_posted}

        await self.campaigns_col.update_one({"_id": ObjectId(campaign_id)}, update_ops)

    async def clear_campaign_error(self, campaign_id: str, user_id: str) -> bool:
        """Xóa cảnh báo lỗi cũ của chiến dịch."""
        res = await self.campaigns_col.update_one(
            {"_id": ObjectId(campaign_id), "user_id": str(user_id)},
            {"$set": {"last_error": None, "updated_at": to_vn_iso(get_vn_now())}},
        )
        return res.modified_count > 0

    async def is_video_already_posted(
        self,
        user_id: str,
        video_item_id: str,
        video_url: Optional[str] = None,
        only_today: bool = False,
    ) -> bool:
        """Kiểm tra video Douyin (qua ID hoặc link) đã được lưu vào database và đăng chưa."""
        conditions: List[Dict[str, Any]] = [{"video_item_id": str(video_item_id)}]
        if video_url:
            conditions.append({"video_url": str(video_url)})

        query: Dict[str, Any] = {
            "user_id": str(user_id),
            "$or": conditions,
        }
        if only_today:
            today_str = get_vn_now().strftime("%Y-%m-%d")
            query["published_date"] = today_str

        # 1. Kiểm tra trong kho video đã đăng chính thức
        found_posted = await self.posted_videos_col.find_one(query)
        if found_posted:
            return True

        # 2. Kiểm tra trong logs đang xử lý hoặc thành công
        log_query: Dict[str, Any] = {
            "user_id": str(user_id),
            "$or": conditions,
            "status": {"$in": ["success", "partial", "processing"]},
        }
        if only_today:
            today_start = get_vn_now().strftime("%Y-%m-%dT00:00:00")
            log_query["created_at"] = {"$gte": today_start}

        found_log = await self.logs_col.find_one(log_query)
        if found_log:
            return True

        # 3. Kiểm tra liên thông trong dubbing_tasks (Voice Studio / tác vụ thủ công)
        dub_query: Dict[str, Any] = {
            "user_id": str(user_id),
            "status": {"$in": ["pending", "processing", "completed"]},
            "$or": [
                {"source_url": {"$regex": str(video_item_id)}},
                {"video_url": {"$regex": str(video_item_id)}},
            ],
        }
        if video_url:
            dub_query["$or"].extend([{"source_url": str(video_url)}, {"video_url": str(video_url)}])
        found_dub = await self.db["dubbing_tasks"].find_one(dub_query)
        return bool(found_dub)

    async def record_posted_video(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Lưu video đã đăng vào database kèm ID và Link để chống trùng lặp tuyệt đối."""
        now_dt = get_vn_now()
        doc = {
            **data,
            "user_id": str(user_id),
            "published_date": now_dt.strftime("%Y-%m-%d"),
            "created_at": to_vn_iso(now_dt),
        }
        res = await self.posted_videos_col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return self._doc_to_dict(doc)

    async def get_posted_videos(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy danh sách các video đã lưu trong database chống trùng."""
        cursor = self.posted_videos_col.find({"user_id": str(user_id)}).sort("created_at", -1).limit(limit)
        items = []
        async for doc in cursor:
            items.append(self._doc_to_dict(doc))
        return items

    async def create_log(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = to_vn_iso(get_vn_now())
        doc = {**data, "created_at": now}
        res = await self.logs_col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return self._doc_to_dict(doc)

    async def update_log(self, log_id: str, update_dict: Dict[str, Any]) -> bool:
        """Cập nhật thông tin và trạng thái log xử lý video."""
        if not log_id:
            return False
        update_dict["updated_at"] = to_vn_iso(get_vn_now())
        res = await self.logs_col.update_one(
            {"_id": ObjectId(log_id)},
            {"$set": update_dict},
        )
        return res.modified_count > 0

    async def get_logs(
        self, user_id: str, campaign_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"user_id": str(user_id)}
        if campaign_id:
            query["campaign_id"] = str(campaign_id)
        cursor = self.logs_col.find(query).sort("created_at", -1).limit(limit)
        items = []
        async for doc in cursor:
            items.append(self._doc_to_dict(doc))
        return items

