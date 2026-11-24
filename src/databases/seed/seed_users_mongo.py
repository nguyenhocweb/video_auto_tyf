import asyncio
from src.modules.shared.auth.repository import AuthMongoRepository
from src.modules.shared.auth.security import hash_password


async def seed_users():
    repo = AuthMongoRepository()
    print(">>> Starting users seeding to MongoDB...")

    # 1. Tai khoan Super Admin
    admin_email = "admin@videoai.com"
    existing_admin = await repo.get_by_email(admin_email)
    if not existing_admin:
        admin_doc = await repo.create_user({
            "email": admin_email,
            "password_hash": hash_password("admin123456"),
            "full_name": "Quan Tri Vien He Thong (Super Admin)",
            "role": "ADMIN",
            "status": "ACTIVE",
        })
        print(f"[OK] Created Admin user: {admin_email} (ID: {admin_doc['id']})")
    else:
        print(f"[INFO] Admin user already exists: {admin_email} (ID: {existing_admin['id']})")

    # 2. Tai khoan Nguoi dung thuong (Creator User)
    user_email = "user@videoai.com"
    existing_user = await repo.get_by_email(user_email)
    if not existing_user:
        user_doc = await repo.create_user({
            "email": user_email,
            "password_hash": hash_password("user123456"),
            "full_name": "Nguoi Dung Sang Tao (Creator User)",
            "role": "USER",
            "status": "ACTIVE",
        })
        print(f"[OK] Created User: {user_email} (ID: {user_doc['id']})")
    else:
        print(f"[INFO] User already exists: {user_email} (ID: {existing_user['id']})")

    total = await repo.count_users()
    print(f"[SUCCESS] Done seeding users! Total {total} users in MongoDB.")


if __name__ == "__main__":
    asyncio.run(seed_users())
