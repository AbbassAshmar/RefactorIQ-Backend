from __future__ import annotations

import uuid

from app.core.enums import RefactorQueueStatus
from app.core.exceptions.domain_exceptions import ConflictError, EntityNotFoundError, PersistenceError
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.refactor_queue.refactor_queue_dtos import (
    RefactorQueueItemResponse,
    RefactorQueueListResponse,
)
from app.refactor_queue.refactor_queue_repository import RefactorQueueRepository


class RefactorQueueService:
    def __init__(self, repository: RefactorQueueRepository) -> None:
        self._repository = repository

    def list_items(self, user_id: uuid.UUID, project_id: uuid.UUID) -> RefactorQueueListResponse:
        try:
            items = self._repository.list_for_project(user_id, project_id)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("project", project_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list refactor queue") from exc
        return RefactorQueueListResponse(
            project_id=project_id,
            items=[RefactorQueueItemResponse.model_validate(item) for item in items],
        )

    def add_item(self, user_id: uuid.UUID, project_id: uuid.UUID, file_path: str) -> RefactorQueueItemResponse:
        try:
            item = self._repository.create(user_id, project_id, file_path)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("project", project_id) from exc
        except DuplicateRecordException as exc:
            raise ConflictError("File is already in the refactor queue") from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to add file to refactor queue") from exc
        return RefactorQueueItemResponse.model_validate(item)

    def move_item(
        self,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        status: RefactorQueueStatus,
        position: int,
    ) -> RefactorQueueItemResponse:
        try:
            item = self._repository.move(user_id, item_id, status, position)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("refactor queue item", item_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to move refactor queue item") from exc
        return RefactorQueueItemResponse.model_validate(item)

    def delete_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
        try:
            self._repository.delete(user_id, item_id)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("refactor queue item", item_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to delete refactor queue item") from exc
