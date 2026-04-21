from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.exceptions.repository_exceptions import DatabaseOperationException
from app.models import Role
from app.schemas.role import RoleInternal


class RoleRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, role_id: uuid.UUID) -> RoleInternal | None:
        try:
            stmt = select(Role).where(Role.id == role_id)
            role = self._db.execute(stmt).scalar_one_or_none()
            return RoleInternal.model_validate(role) if role else None
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to load role by id",
                details={"role_id": str(role_id)},
            ) from exc

    def get_by_name(self, role_name: UserRole | str) -> RoleInternal | None:
        normalized_name = (
            role_name.value if isinstance(role_name, UserRole) else str(role_name)
        )
        try:
            stmt = select(Role).where(Role.name == normalized_name)
            role = self._db.execute(stmt).scalar_one_or_none()
            return RoleInternal.model_validate(role) if role else None
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to load role by name",
                details={"name": normalized_name},
            ) from exc
