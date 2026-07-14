from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai_explanations.ai_explanations_repository import AiExplanationRepository
from app.ai_explanations.ai_explanations_service import AiExplanationService
from app.config import settings
from app.core.database import get_db
from app.utils.llm_provider import GeminiLlmProvider, LlmProvider


def get_llm_provider() -> LlmProvider:
    return GeminiLlmProvider(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
    )


def get_ai_explanation_repository(db: Session = Depends(get_db)) -> AiExplanationRepository:
    return AiExplanationRepository(db)


def get_ai_explanation_service(
    repository: AiExplanationRepository = Depends(get_ai_explanation_repository),
    provider: LlmProvider = Depends(get_llm_provider),
) -> AiExplanationService:
    return AiExplanationService(repository, provider)
