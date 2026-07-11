from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.overview.repository import OverviewRepository
from app.overview.service import OverviewService


def get_overview_repository(db: Session = Depends(get_db)) -> OverviewRepository:
    return OverviewRepository(db)


def get_overview_service(
    repository: OverviewRepository = Depends(get_overview_repository),
) -> OverviewService:
    return OverviewService(repository)
