from fastapi import APIRouter, Depends, status
from src.modules.shared.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse,
)
from src.modules.shared.auth.service import AuthService
from src.modules.shared.auth.dependencies import get_current_user

auth_router = APIRouter(prefix="/auth", tags=["Authentication & Roles"])


def get_auth_service() -> AuthService:
    return AuthService()


@auth_router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Đăng nhập chung hệ thống (Tự động nhận diện Admin hoặc User qua Token)",
)
async def login_endpoint(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await service.login(payload)


@auth_router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Cấp lại Access Token và Refresh Token mới",
)
async def refresh_tokens_endpoint(
    payload: RefreshTokenRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await service.refresh_tokens(payload)


@auth_router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản người dùng mới",
)
async def register_endpoint(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await service.register(payload)


@auth_router.get(
    "/me",
    response_model=UserResponse,
    summary="Lấy thông tin tài khoản đang đăng nhập",
)
async def get_me_endpoint(
    current_user: dict = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    return await service.get_current_user_profile(current_user["id"])


@auth_router.get(
    "/demo-accounts",
    summary="Lấy thông tin tài khoản mẫu để hỗ trợ kiểm thử",
)
async def get_demo_accounts_endpoint():
    repo = AuthService().repo
    await repo.init_default_accounts()
    return {
        "accounts": [
            {
                "email": "user@videoai.com",
                "password": "user123456",
                "role": "USER",
                "label": "Tài khoản Người Dùng Thường",
                "description": "Toàn quyền sử dụng AI Voice Studio, thu âm và huấn luyện giọng",
            },
            {
                "email": "admin@videoai.com",
                "password": "admin123456",
                "role": "ADMIN",
                "label": "Tài khoản Super Admin",
                "description": "Toàn quyền quản trị hệ thống, Users, Voices và Dashboard",
            },
        ]
    }
