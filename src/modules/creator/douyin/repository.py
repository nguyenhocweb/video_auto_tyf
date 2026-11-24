import asyncio
import logging
from typing import Dict, Any, Optional, List
from pymongo import MongoClient
from src.core.config import settings
from src.core.utils.date_utils import get_vn_now, to_vn_iso

logger = logging.getLogger("douyin_repository")


class DouyinMongoRepository:
    """Repository quản lý phiên đăng nhập Douyin trong MongoDB.
    
    Sử dụng PyMongo kết hợp asyncio.to_thread để đảm bảo tính thread-safe tuyệt đối
    khi gọi callback từ các event loop phụ (như ProactorLoopThread trên Windows).
    """

    def __init__(self):
        self._url = settings.DATABASE_URL
        self._db_name = settings.MONGO_DB_NAME

    def _get_col(self):
        client = MongoClient(self._url, serverSelectionTimeoutMS=3000)
        return client, client[self._db_name]["douyin_sessions"]

    @staticmethod
    def _doc_to_dict(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not doc:
            return None
        res = dict(doc)
        if "_id" in res:
            res["id"] = str(res["_id"])
            del res["_id"]
        for k in ["created_at", "updated_at", "last_connected_at"]:
            if k in res and res[k]:
                res[k] = to_vn_iso(res[k])
        return res

    def _get_active_session_sync(self, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        client, col = self._get_col()
        try:
            query: Dict[str, Any] = {"is_active": True}
            if user_id:
                query["user_id"] = str(user_id)
            doc = col.find_one(query, sort=[("updated_at", -1)])
            return self._doc_to_dict(doc)
        finally:
            client.close()

    async def get_active_session(self, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Lấy phiên đăng nhập Douyin đang hoạt động gần nhất."""
        return await asyncio.to_thread(self._get_active_session_sync, user_id)

    def _save_session_sync(
        self, user_id: str, cookies_str: str, cookies_list: List[Dict[str, Any]], account_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        client, col = self._get_col()
        try:
            now = to_vn_iso(get_vn_now())
            col.update_many(
                {"user_id": str(user_id), "is_active": True},
                {"$set": {"is_active": False, "updated_at": now}},
            )
            doc = {
                "user_id": str(user_id),
                "cookies_str": cookies_str,
                "cookies_list": cookies_list,
                "nickname": account_info.get("name") or account_info.get("screen_name") or "Douyin User",
                "avatar_url": account_info.get("avatar_url") or "",
                "uid": str(account_info.get("user_id") or account_info.get("uid") or ""),
                "sec_uid": str(account_info.get("sec_uid") or ""),
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "last_connected_at": now,
            }
            res = col.insert_one(doc)
            doc["id"] = str(res.inserted_id)
            logger.info(f"Đã lưu phiên Douyin thành công cho user={user_id}, uid={doc['uid']}")
            return doc
        finally:
            client.close()

    async def save_session(
        self, user_id: str, cookies_str: str, cookies_list: List[Dict[str, Any]], account_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Lưu hoặc cập nhật phiên đăng nhập Douyin thành công."""
        return await asyncio.to_thread(self._save_session_sync, user_id, cookies_str, cookies_list, account_info)

    def _deactivate_session_sync(self, user_id: str) -> bool:
        client, col = self._get_col()
        try:
            now = to_vn_iso(get_vn_now())
            res = col.update_many(
                {"user_id": str(user_id), "is_active": True},
                {"$set": {"is_active": False, "updated_at": now}},
            )
            logger.info(f"Đã vô hiệu hóa {res.modified_count} phiên Douyin của user={user_id}")
            return res.modified_count > 0
        finally:
            client.close()

    async def deactivate_session(self, user_id: str) -> bool:
        """Đăng xuất / Vô hiệu hóa phiên Douyin của người dùng."""
        return await asyncio.to_thread(self._deactivate_session_sync, user_id)
