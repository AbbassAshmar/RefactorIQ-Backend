from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai_explanations.ai_explanations_service import AiExplanationService
from app.ai_explanations.dependencies import get_ai_explanation_service
from app.core.database import get_db
from app.overview.overview_repository import OverviewRepository
from app.overview.overview_service import OverviewService


def get_overview_repository(db: Session = Depends(get_db)) -> OverviewRepository:
    return OverviewRepository(db)


def get_overview_service(
    repository: OverviewRepository = Depends(get_overview_repository),
    ai_explanation_service: AiExplanationService = Depends(get_ai_explanation_service),
) -> OverviewService:
    return OverviewService(repository, ai_explanation_service=ai_explanation_service)
