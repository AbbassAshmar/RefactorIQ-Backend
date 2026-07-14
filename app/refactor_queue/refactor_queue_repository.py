from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.enums import RefactorQueueStatus
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.models import Project, RefactorQueueItem


class RefactorQueueRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> list[RefactorQueueItem]:
        try:
            self._ensure_project_access(user_id, project_id)
            return list(
                self._db.scalars(
                    select(RefactorQueueItem)
                    .where(RefactorQueueItem.project_id == project_id)
                    .order_by(self._status_order(), RefactorQueueItem.position, RefactorQueueItem.created_at)
                ).all()
            )
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Unable to list refactor queue items") from exc

    def create(self, user_id: uuid.UUID, project_id: uuid.UUID, file_path: str) -> RefactorQueueItem:
        try:
            self._ensure_project_access(user_id, project_id)
            next_position = self._db.scalar(
                select(func.coalesce(func.max(RefactorQueueItem.position), -1) + 1).where(
                    RefactorQueueItem.project_id == project_id,
                    RefactorQueueItem.status == RefactorQueueStatus.PENDING,
                )
            )
            item = RefactorQueueItem(
                project_id=project_id,
                file_path=file_path.strip(),
                status=RefactorQueueStatus.PENDING,
                position=int(next_position or 0),
            )
            self._db.add(item)
            self._db.commit()
            self._db.refresh(item)
            return item
        except RecordNotFoundException:
            raise
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateRecordException("File is already in the refactor queue") from exc
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException("Unable to add file to refactor queue") from exc

    def move(
        self,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        status: RefactorQueueStatus,
        position: int,
    ) -> RefactorQueueItem:
        try:
            item = self._get_owned_item(user_id, item_id)
            items = list(
                self._db.scalars(
                    select(RefactorQueueItem)
                    .where(RefactorQueueItem.project_id == item.project_id)
                    .order_by(self._status_order(), RefactorQueueItem.position, RefactorQueueItem.created_at)
                ).all()
            )
            groups = {queue_status: [] for queue_status in RefactorQueueStatus}
            for current in items:
                if current.id != item.id:
                    groups[current.status].append(current)
            target_group = groups[status]
            target_group.insert(min(position, len(target_group)), item)
            for queue_status, group in groups.items():
                for index, current in enumerate(group):
                    current.status = queue_status
                    current.position = index
            self._db.commit()
            self._db.refresh(item)
            return item
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException("Unable to move refactor queue item") from exc

    def delete(self, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
        try:
            item = self._get_owned_item(user_id, item_id)
            project_id = item.project_id
            status = item.status
            self._db.delete(item)
            self._db.flush()
            remaining = list(
                self._db.scalars(
                    select(RefactorQueueItem)
                    .where(
                        RefactorQueueItem.project_id == project_id,
                        RefactorQueueItem.status == status,
                    )
                    .order_by(RefactorQueueItem.position, RefactorQueueItem.created_at)
                ).all()
            )
            for index, current in enumerate(remaining):
                current.position = index
            self._db.commit()
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException("Unable to delete refactor queue item") from exc

    def _ensure_project_access(self, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        exists = self._db.scalar(
            select(Project.id).where(Project.id == project_id, Project.user_id == user_id)
        )
        if exists is None:
            raise RecordNotFoundException("Project not found")

    @staticmethod
    def _status_order():
        return case(
            (RefactorQueueItem.status == RefactorQueueStatus.PENDING, 0),
            (RefactorQueueItem.status == RefactorQueueStatus.IN_PROGRESS, 1),
            (RefactorQueueItem.status == RefactorQueueStatus.COMPLETED, 2),
            else_=3,
        )

    def _get_owned_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> RefactorQueueItem:
        item = self._db.scalar(
            select(RefactorQueueItem)
            .join(Project, Project.id == RefactorQueueItem.project_id)
            .where(RefactorQueueItem.id == item_id, Project.user_id == user_id)
        )
        if item is None:
            raise RecordNotFoundException("Refactor queue item not found")
        return item
