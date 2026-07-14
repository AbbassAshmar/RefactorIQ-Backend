from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai_explanations.ai_explanations_service import AiExplanationService
from app.ai_explanations.dependencies import get_ai_explanation_service, get_llm_provider
from app.core.database import get_db
from app.files.files_repository import FileRepository
from app.files.files_service import FileService
from app.utils.llm_provider import LlmProvider


def get_file_repository(db: Session = Depends(get_db)) -> FileRepository:
    return FileRepository(db)


def get_file_service(
    repository: FileRepository = Depends(get_file_repository),
    ai_explanation_service: AiExplanationService = Depends(get_ai_explanation_service),
) -> FileService:
    return FileService(repository, ai_explanation_service=ai_explanation_service)
