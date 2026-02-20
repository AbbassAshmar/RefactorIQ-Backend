"""User management routes (controllers).

All endpoints require the ``manage-users`` permission (admins only).

* ``GET    /users``          – paginated user list
* ``GET    /users/{user_id}`` – single user
* ``PATCH  /users/{user_id}`` – update user
* ``DELETE /users/{user_id}`` – delete user
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.auth.utils import get_current_payload, require_permission
from app.core.enums import UserRole
from app.dependencies import get_user_service
from app.schemas.auth import TokenPayload
from app.schemas.user import UserUpdate
from app.users.services.service import UserService
from app.utils.response import ApiResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/")
def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    role: UserRole | None = None,
    user_service: UserService = Depends(get_user_service),
    payload: TokenPayload = Depends(require_permission("manage-users")),
):
    user_service.get_user(uuid.UUID(payload.sub))
    data = user_service.list_users(page=page, size=size, role=role)
    return ApiResponse.success(data=data.model_dump())


@router.get("/{user_id}")
def get_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
    payload: TokenPayload = Depends(require_permission("manage-users")),
):
    user_service.get_user(uuid.UUID(payload.sub))
    data = user_service.get_user(user_id)
    return ApiResponse.success(data=data.model_dump())


@router.patch("/{user_id}")
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    user_service: UserService = Depends(get_user_service),
    payload: TokenPayload = Depends(require_permission("manage-users")),
):
    user_service.get_user(uuid.UUID(payload.sub))
    data = user_service.update_user(user_id, body)
    return ApiResponse.success(data=data.model_dump())


@router.delete("/{user_id}")
def delete_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
    payload: TokenPayload = Depends(require_permission("manage-users")),
):
    user_service.get_user(uuid.UUID(payload.sub))
    user_service.delete_user(user_id)
    return ApiResponse.success(data={"message": "User deleted successfully"})
