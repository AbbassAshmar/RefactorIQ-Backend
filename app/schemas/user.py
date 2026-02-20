"""User Pydantic schemas – request / response contracts and internal DTO."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.core.enums import UserRole


# ── Request schemas ──────────────────────────────────────────


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str | None = None
    role: UserRole = UserRole.CLIENT
    github_username: str | None = None
    github_id: int | None = None


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = None
    is_active: bool | None = None
    role: UserRole | None = None


# ── Response schemas ─────────────────────────────────────────


class UserResponse(BaseModel):
    """Public-facing user representation – no sensitive fields."""

    id: uuid.UUID
    email: str
    username: str
    role: UserRole
    github_username: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Internal DTO ─────────────────────────────────────────────


class UserInternal(BaseModel):
    """Full user record for internal service / repository use.
    Never return directly from an API endpoint.
    """

    id: uuid.UUID
    email: str
    username: str
    password: str | None = None
    role: UserRole
    github_access_token: str | None = None
    github_username: str | None = None
    github_id: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
