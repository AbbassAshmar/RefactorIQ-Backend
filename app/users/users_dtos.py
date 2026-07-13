"""User and role DTOs."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.core.enums import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str | None = None
    role_id: uuid.UUID | None = None
    github_username: str | None = None
    github_id: int | None = None


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = None
    is_active: bool | None = None
    role_id: uuid.UUID | None = None


class UserResponse(BaseModel):
    """Public-facing user representation without sensitive fields."""

    id: uuid.UUID
    email: str
    username: str
    role_id: uuid.UUID | None = None
    role: UserRole | None = None
    github_username: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserInternal(BaseModel):
    """Full user record for internal service and repository use."""

    id: uuid.UUID
    email: str
    username: str
    password: str | None = None
    role_id: uuid.UUID | None = None
    role: UserRole | None = None
    github_access_token: str | None = None
    github_username: str | None = None
    github_id: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoleInternal(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)
