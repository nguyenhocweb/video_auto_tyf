import datetime
import uuid
from typing import Dict, Any, Optional, List
from bson import ObjectId
from src.modules.shared.voice.repository_mongo import VoiceMongoRepository
from src.modules.shared.auth.security import hash_password


class AuthMongoRepository:
    def __init__(self):
        self._shared = VoiceMongoRepository()
        self.db = self._shared.db
        self.users_col = self.db["users"]

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        doc = await self.users_col.find_one({"email": email.strip().lower()})
        if doc:
            doc["id"] = str(doc["_id"])
        return doc

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        query = {"_id": ObjectId(user_id)} if ObjectId.is_valid(user_id) else {"_id": user_id}
        doc = await self.users_col.find_one(query)
        if doc:
            doc["id"] = str(doc["_id"])
        return doc

    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.datetime.now(datetime.timezone.utc)
        doc = {
            "email": user_data["email"].strip().lower(),
            "password_hash": user_data["password_hash"],
            "full_name": user_data.get("full_name", "User"),
            "role": user_data.get("role", "CREATOR"),
            "status": user_data.get("status", "ACTIVE"),
            "created_at": now,
            "updated_at": now,
        }
        res = await self.users_col.insert_one(doc)
        doc["id"] = str(res.inserted_id)
        doc["_id"] = res.inserted_id
        return doc

    async def list_users(
        self, skip: int = 0, limit: int = 50, role: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        filter_q: Dict[str, Any] = {}
        if role:
            filter_q["role"] = role

        cursor = self.users_col.find(filter_q).sort("created_at", -1).skip(skip).limit(limit)
        users = []
        async for doc in cursor:
            doc["id"] = str(doc["_id"])
            users.append(doc)
        return users

    async def count_users(self) -> int:
        return await self.users_col.count_documents({})

    async def update_user(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        query = {"_id": ObjectId(user_id)} if ObjectId.is_valid(user_id) else {"_id": user_id}
        update_data["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
        res = await self.users_col.update_one(query, {"$set": update_data})
        return res.modified_count > 0

    async def init_default_accounts(self) -> None:
        """Tự động khởi tạo 2 tài khoản mẫu Admin và Creator nếu chưa có."""
        admin = await self.get_by_email("admin@videoai.com")
        if not admin:
            await self.create_user({
                "email": "admin@videoai.com",
                "password_hash": hash_password("admin123456"),
                "full_name": "Quản Trị Viên Hệ Thống (Admin)",
                "role": "ADMIN",
                "status": "ACTIVE",
            })

        creator = await self.get_by_email("creator@videoai.com")
        if not creator:
            await self.create_user({
                "email": "creator@videoai.com",
                "password_hash": hash_password("user123456"),
                "full_name": "Người Dùng Sáng Tạo (Creator Pro)",
                "role": "CREATOR",
                "status": "ACTIVE",
            })

