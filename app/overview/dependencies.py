from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.files.dependencies import get_llm_provider
from app.overview.overview_repository import OverviewRepository
from app.overview.overview_service import OverviewService
from app.utils.llm_provider import LlmProvider


def get_overview_repository(db: Session = Depends(get_db)) -> OverviewRepository:
    return OverviewRepository(db)


def get_overview_service(
    repository: OverviewRepository = Depends(get_overview_repository),
    summary_provider: LlmProvider = Depends(get_llm_provider),
) -> OverviewService:
    return OverviewService(repository, summary_provider)
