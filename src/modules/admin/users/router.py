from fastapi import APIRouter, Depends, HTTPException, status
from src.modules.shared.auth.dependencies import require_admin
from src.modules.shared.auth.repository import AuthMongoRepository
from src.modules.shared.auth.schemas import UserUpdateRoleRequest, UserUpdateStatusRequest

admin_users_router = APIRouter(prefix="/users", tags=["Admin - User Management"])


@admin_users_router.get(
    "",
    summary="Danh sách người dùng hệ thống",
)
async def list_users_endpoint(
    skip: int = 0,
    limit: int = 50,
    role: str = None,
    _: dict = Depends(require_admin),
):
    repo = AuthMongoRepository()
    users = await repo.list_users(skip=skip, limit=limit, role=role)
    total = await repo.count_users()

    clean_users = []
    for u in users:
        clean_users.append({
            "id": u["id"],
            "email": u["email"],
            "full_name": u.get("full_name", ""),
            "role": u.get("role", "CREATOR"),
            "status": u.get("status", "ACTIVE"),
            "created_at": str(u.get("created_at", "")),
        })

    return {"total": total, "users": clean_users}


@admin_users_router.patch(
    "/{user_id}/role",
    summary="Thay đổi vai trò người dùng (ADMIN hoặc CREATOR)",
)
async def update_user_role_endpoint(
    user_id: str,
    payload: UserUpdateRoleRequest,
    current_admin: dict = Depends(require_admin),
):
    if user_id == current_admin["id"] and payload.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn không thể tự hạ quyền Admin của chính mình",
        )

    repo = AuthMongoRepository()
    updated = await repo.update_user(user_id, {"role": payload.role})
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    return {"message": f"Đã cập nhật vai trò người dùng thành {payload.role}", "user_id": user_id}


@admin_users_router.patch(
    "/{user_id}/status",
    summary="Khóa hoặc mở khóa người dùng (ACTIVE hoặc BLOCKED)",
)
async def update_user_status_endpoint(
    user_id: str,
    payload: UserUpdateStatusRequest,
    current_admin: dict = Depends(require_admin),
):
    if user_id == current_admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bạn không thể tự khóa tài khoản của chính mình",
        )

    repo = AuthMongoRepository()
    updated = await repo.update_user(user_id, {"status": payload.status})
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    return {"message": f"Đã cập nhật trạng thái người dùng thành {payload.status}", "user_id": user_id}

