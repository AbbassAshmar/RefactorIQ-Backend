"""User business-logic service.

Orchestrates user CRUD operations via ``UserRepository``.
Has **zero** knowledge of SQLAlchemy or the database – it only works with
Pydantic schemas.
"""

from __future__ import annotations

import uuid

from app.core.enums import UserRole
from app.core.exceptions.domain_exceptions import ConflictError, EntityNotFoundError
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.core.security import hash_password
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserInternal, UserResponse, UserUpdate
from app.users.repositories.role_repository import RoleRepository
from app.users.repositories.repository import UserRepository


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        role_repository: RoleRepository,
    ) -> None:
        self._repo = repository
        self._role_repo = role_repository

    # ── Read ─────────────────────────────────────────────────

    def get_user_internal(self, user_id: uuid.UUID) -> UserInternal:
        try:
            user = self._repo.get_by_id(user_id)
            if not user:
                raise EntityNotFoundError("user", user_id)
            return user
        except DatabaseOperationException as exc:
            raise ConflictError("Unable to retrieve user") from exc

    def get_user(self, user_id: uuid.UUID) -> UserResponse:
        user = self.get_user_internal(user_id)
        return UserResponse.model_validate(user.model_dump())

    def list_users(
        self,
        *,
        page: int = 1,
        size: int = 20,
        role: UserRole | None = None,
    ) -> PaginatedResponse[UserResponse]:
        try:
            users, total = self._repo.list_users(page=page, size=size, role=role)
            items = [UserResponse.model_validate(u.model_dump()) for u in users]
            pages = (total + size - 1) // size if size else 0
            return PaginatedResponse(
                items=items, total=total, page=page, size=size, pages=pages
            )
        except DatabaseOperationException as exc:
            raise ConflictError("Unable to list users") from exc

    def create_admin(
        self, email: str, full_name: str, password: str
    ) -> UserResponse:
        """Create an admin user with email + password."""
        try:
            if self._repo.get_by_email(email):
                raise ConflictError("User with this email already exists")

            admin_role = self._role_repo.get_by_name(UserRole.ADMIN)
            if not admin_role:
                raise ConflictError("Default admin role is not configured")

            hashed = hash_password(password)
            data = UserCreate(
                email=email,
                username=full_name,
            )
            user = self._repo.create(
                data,
                hashed_password=hashed,
                role_id=admin_role.id,
            )
            return UserResponse.model_validate(user.model_dump())
        except DuplicateRecordException as exc:
            raise ConflictError("User with this email already exists") from exc
        except DatabaseOperationException as exc:
            raise ConflictError("Unable to create user") from exc

    def update_user(
        self, user_id: uuid.UUID, update_data: UserUpdate
    ) -> UserResponse:
        try:
            if not self._repo.get_by_id(user_id):
                raise EntityNotFoundError("user", user_id)

            fields = update_data.model_dump(exclude_unset=True)

            role_id = fields.get("role_id")
            if role_id is not None and not self._role_repo.get_by_id(role_id):
                raise ConflictError("Invalid role_id")

            updated = self._repo.update(user_id, fields)
            return UserResponse.model_validate(updated.model_dump())
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("user", user_id) from exc
        except DuplicateRecordException as exc:
            raise ConflictError("User update conflicts with existing data") from exc
        except DatabaseOperationException as exc:
            raise ConflictError("Unable to update user") from exc

    # ── Delete ───────────────────────────────────────────────

    def delete_user(self, user_id: uuid.UUID) -> None:
        try:
            self._repo.delete(user_id)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("user", user_id) from exc
        except DatabaseOperationException as exc:
            raise ConflictError("Unable to delete user") from exc
