import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.models.user import UserRole


class UserRegister(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    username: str | None = None
    display_name: str
    password: str
    confirm_password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^\+?[0-9]{7,15}$", v):
            raise ValueError("Invalid phone number format")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip().lower()
            if len(v) < 3:
                raise ValueError("Username must be at least 3 characters")
            if len(v) > 30:
                raise ValueError("Username must be at most 30 characters")
            if not re.match(r"^[a-z0-9_]+$", v):
                raise ValueError("Username can only contain lowercase letters, numbers, and underscores")
        return v


class UserLogin(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    username: str | None = None
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None = None
    phone: str | None = None
    username: str | None = None
    display_name: str
    role: UserRole
    is_active: bool
    is_verified: bool
    timezone: str
    language: str
    avatar_url: str | None = None
    created_at: datetime


class UserUpdate(BaseModel):
    display_name: str | None = None
    username: str | None = None
    timezone: str | None = None
    language: str | None = None
    avatar_url: str | None = None


class AdminUserCreate(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    username: str | None = None
    display_name: str
    password: str
    role: UserRole = UserRole.ADMIN


class AdminUserUpdate(BaseModel):
    display_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class FavoriteCreate(BaseModel):
    entity_type: str
    entity_id: uuid.UUID


class FavoriteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    created_at: datetime


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v


class GoogleLoginRequest(BaseModel):
    id_token: str
