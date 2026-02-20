from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.models import User
from app.schemas.user import UserCreate, UserInternal


class UserRepository:
    def __init__(self, db: Session) -> None:
        self._db = db


    def get_by_id(self, user_id: uuid.UUID) -> UserInternal | None:
        try:
            stmt = select(User).where(User.id == user_id)
            user = self._db.execute(stmt).scalar_one_or_none()
            return UserInternal.model_validate(user) if user else None
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to load user by id",
                details={"user_id": str(user_id)},
            ) from exc

    def get_by_email(self, email: str) -> UserInternal | None:
        try:
            stmt = select(User).where(User.email == email)
            user = self._db.execute(stmt).scalar_one_or_none()
            return UserInternal.model_validate(user) if user else None
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to load user by email",
                details={"email": email},
            ) from exc

    def get_by_github_id(self, github_id: int) -> UserInternal | None:
        try:
            stmt = select(User).where(User.github_id == github_id)
            user = self._db.execute(stmt).scalar_one_or_none()
            return UserInternal.model_validate(user) if user else None
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to load user by GitHub id",
                details={"github_id": github_id},
            ) from exc


    def create(
        self,
        data: UserCreate,
        *,
        hashed_password: str | None = None,
        github_access_token: str | None = None,
    ) -> UserInternal:
        user = User(
            email=data.email,
            username=data.username,
            role=data.role,
            password=hashed_password,
            github_username=data.github_username,
            github_id=data.github_id,
            github_access_token=github_access_token,
        )
        try:
            self._db.add(user)
            self._db.commit()
            self._db.refresh(user)
            return UserInternal.model_validate(user)
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateRecordException(
                "User already exists",
                details={"email": data.email},
            ) from exc
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException("Failed to create user") from exc


    def update(
        self, user_id: uuid.UUID, fields: dict
    ) -> UserInternal | None:
        """Update arbitrary columns on a user row.

        ``fields`` should only contain keys that map to real ``User`` column
        names.  Values are applied as-is (the caller is responsible for any
        hashing / encryption).
        """
        try:
            stmt = select(User).where(User.id == user_id)
            user = self._db.execute(stmt).scalar_one_or_none()
            if not user:
                raise RecordNotFoundException(
                    "User not found",
                    details={"user_id": str(user_id)},
                )

            for key, value in fields.items():
                setattr(user, key, value)

            self._db.commit()
            self._db.refresh(user)
            return UserInternal.model_validate(user)
        except RecordNotFoundException:
            raise
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateRecordException("User update conflicts with existing data") from exc
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to update user",
                details={"user_id": str(user_id)},
            ) from exc


    def delete(self, user_id: uuid.UUID) -> bool:
        try:
            stmt = select(User).where(User.id == user_id)
            user = self._db.execute(stmt).scalar_one_or_none()
            if not user:
                raise RecordNotFoundException(
                    "User not found",
                    details={"user_id": str(user_id)},
                )
            self._db.delete(user)
            self._db.commit()
            return True
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to delete user",
                details={"user_id": str(user_id)},
            ) from exc


    def list_users(
        self,
        *,
        page: int = 1,
        size: int = 20,
        role: UserRole | None = None,
    ) -> tuple[list[UserInternal], int]:
        """Return a page of users and the total count."""
        try:
            base = select(User)
            count_stmt = select(func.count()).select_from(User)

            if role is not None:
                base = base.where(User.role == role)
                count_stmt = count_stmt.where(User.role == role)

            total: int = self._db.execute(count_stmt).scalar() or 0

            stmt = (
                base.order_by(User.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
            rows = self._db.execute(stmt).scalars().all()
            return [UserInternal.model_validate(u) for u in rows], total
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to list users") from exc


    def update_github_token(
        self, user_id: uuid.UUID, encrypted_token: str
    ) -> bool:
        self.update(user_id, {"github_access_token": encrypted_token})
        return True
