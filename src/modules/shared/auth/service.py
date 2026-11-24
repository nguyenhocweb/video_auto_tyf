import datetime
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from src.modules.shared.auth.repository import AuthMongoRepository
from src.modules.shared.auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from src.modules.shared.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
    UserResponse,
    TokenResponse,
)


class AuthService:
    def __init__(self):
        self.repo = AuthMongoRepository()

    async def login(self, payload: LoginRequest) -> TokenResponse:
        await self.repo.init_default_accounts()
        user = await self.repo.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.get("password_hash", "")):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email hoặc mật khẩu không chính xác",
            )

        if user.get("status") == "BLOCKED":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tài khoản của bạn đã bị khóa bởi Quản trị viên",
            )

        role = user.get("role", "USER")

        # Cấp cặp Access Token (ngắn hạn) + Refresh Token (dài hạn)
        access_token = create_access_token({
            "sub": user["id"],
            "email": user["email"],
            "role": role,
        })
        refresh_token = create_refresh_token({
            "sub": user["id"],
        })

        created_at_val = user.get("created_at")
        created_str = (
            created_at_val.strftime("%d/%m/%Y %H:%M")
            if isinstance(created_at_val, datetime.datetime)
            else str(created_at_val or "")
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                full_name=user.get("full_name", ""),
                role=role,
                status=user.get("status", "ACTIVE"),
                created_at=created_str,
            ),
        )

    async def refresh_tokens(self, payload: RefreshTokenRequest) -> TokenResponse:
        """Cấp Access Token và Refresh Token mới dựa trên Refresh Token hợp lệ."""
        decoded = decode_refresh_token(payload.refresh_token)
        if not decoded or not decoded.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token không hợp lệ hoặc đã hết hạn",
            )

        user_id = decoded["sub"]
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Người dùng của token không tồn tại",
            )

        if user.get("status") == "BLOCKED":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tài khoản đã bị khóa",
            )

        role = user.get("role", "USER")
        new_access_token = create_access_token({
            "sub": user["id"],
            "email": user["email"],
            "role": role,
        })
        new_refresh_token = create_refresh_token({
            "sub": user["id"],
        })

        created_at_val = user.get("created_at")
        created_str = (
            created_at_val.strftime("%d/%m/%Y %H:%M")
            if isinstance(created_at_val, datetime.datetime)
            else str(created_at_val or "")
        )

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                full_name=user.get("full_name", ""),
                role=role,
                status=user.get("status", "ACTIVE"),
                created_at=created_str,
            ),
        )

    async def register(self, payload: RegisterRequest) -> TokenResponse:
        existing = await self.repo.get_by_email(payload.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email này đã được sử dụng",
            )

        role = "ADMIN" if payload.role == "ADMIN" else "USER"
        user = await self.repo.create_user({
            "email": payload.email,
            "password_hash": hash_password(payload.password),
            "full_name": payload.full_name,
            "role": role,
            "status": "ACTIVE",
        })

        access_token = create_access_token({
            "sub": user["id"],
            "email": user["email"],
            "role": user["role"],
        })
        refresh_token = create_refresh_token({
            "sub": user["id"],
        })

        created_at_val = user.get("created_at")
        created_str = (
            created_at_val.strftime("%d/%m/%Y %H:%M")
            if isinstance(created_at_val, datetime.datetime)
            else str(created_at_val or "")
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                full_name=user["full_name"],
                role=user["role"],
                status=user["status"],
                created_at=created_str,
            ),
        )

    async def get_current_user_profile(self, user_id: str) -> UserResponse:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy người dùng",
            )
        created_at_val = user.get("created_at")
        created_str = (
            created_at_val.strftime("%d/%m/%Y %H:%M")
            if isinstance(created_at_val, datetime.datetime)
            else str(created_at_val or "")
        )
        return UserResponse(
            id=user["id"],
            email=user["email"],
            full_name=user.get("full_name", ""),
            role=user.get("role", "USER"),
            status=user.get("status", "ACTIVE"),
            created_at=created_str,
        )
