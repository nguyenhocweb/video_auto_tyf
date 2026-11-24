from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=2)
    role: str = Field(default="USER")  # "USER" hoặc "ADMIN"


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh Token dài hạn dùng để làm mới Access Token")


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    status: str
    created_at: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    user: UserResponse


class UserUpdateRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(ADMIN|USER|CREATOR)$")


class UserUpdateStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(ACTIVE|BLOCKED)$")
