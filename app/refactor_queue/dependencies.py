from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.refactor_queue.refactor_queue_repository import RefactorQueueRepository
from app.refactor_queue.refactor_queue_service import RefactorQueueService


def get_refactor_queue_repository(db: Session = Depends(get_db)) -> RefactorQueueRepository:
    return RefactorQueueRepository(db)


def get_refactor_queue_service(
    repository: RefactorQueueRepository = Depends(get_refactor_queue_repository),
) -> RefactorQueueService:
    return RefactorQueueService(repository)
