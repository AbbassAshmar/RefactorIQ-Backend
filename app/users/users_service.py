"""User business-logic service.

Orchestrates user CRUD operations via ``UserRepository``.
Has **zero** knowledge of SQLAlchemy or the database – it only works with
Pydantic schemas.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from app.core.enums import UserRole
from app.core.exceptions.domain_exceptions import (
    ConflictError,
    EntityNotFoundError,
    PersistenceError,
)
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.core.security import hash_password
from app.core.common_dtos import PaginatedResponse
from app.users.users_dtos import (
    UserCreate,
    UserInternal,
    UserResponse,
    UserTimelinePoint,
    UserTimelineResponse,
    UserUpdate,
)
from app.users.repositories.role_repository import RoleRepository
from app.users.repositories.user_repository import UserRepository


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
            raise PersistenceError("Unable to retrieve user") from exc

    def get_user(self, user_id: uuid.UUID) -> UserResponse:
        user = self.get_user_internal(user_id)
        return UserResponse.model_validate(user.model_dump())

    def list_users(
        self,
        *,
        page: int = 1,
        size: int = 20,
        role: UserRole | None = None,
        query: str | None = None,
    ) -> PaginatedResponse[UserResponse]:
        try:
            users, total = self._repo.list_users(
                page=page,
                size=size,
                role=role,
                query=query,
            )
            items = [UserResponse.model_validate(u.model_dump()) for u in users]
            pages = (total + size - 1) // size if size else 0
            return PaginatedResponse(
                items=items, total=total, page=page, size=size, pages=pages
            )
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list users") from exc

    def get_users_over_time(
        self,
        *,
        now: datetime | None = None,
    ) -> UserTimelineResponse:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        else:
            current = current.astimezone(timezone.utc)

        current_month = date(current.year, current.month, 1)
        start_month = self._shift_month(current_month, -14)
        next_month = self._shift_month(current_month, 1)
        created_from = datetime.combine(start_month, time.min, tzinfo=timezone.utc)
        created_before = datetime.combine(next_month, time.min, tzinfo=timezone.utc)

        try:
            users = self._repo.list_created_at_between(
                created_from=created_from,
                created_before=created_before,
            )
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to load users over time") from exc

        counts = {self._shift_month(start_month, offset): 0 for offset in range(15)}
        for created_at in users:
            created = (
                created_at.replace(tzinfo=timezone.utc)
                if created_at.tzinfo is None
                else created_at.astimezone(timezone.utc)
            )
            month = date(created.year, created.month, 1)
            if month in counts:
                counts[month] += 1

        return UserTimelineResponse(
            points=[
                UserTimelinePoint(date=month, count=counts[month])
                for month in counts
            ]
        )

    @staticmethod
    def _shift_month(month: date, offset: int) -> date:
        month_index = month.year * 12 + month.month - 1 + offset
        year, zero_based_month = divmod(month_index, 12)
        return date(year, zero_based_month + 1, 1)

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
            raise PersistenceError("Unable to create user") from exc

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
            raise PersistenceError("Unable to update user") from exc

    # ── Delete ───────────────────────────────────────────────

    def delete_user(self, user_id: uuid.UUID) -> None:
        try:
            self._repo.delete(user_id)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("user", user_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to delete user") from exc
