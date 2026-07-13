from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.files.files_repository import FileRepository
from app.files.files_service import FileService
from app.utils.llm_provider import GeminiLlmProvider, LlmProvider


def get_file_repository(db: Session = Depends(get_db)) -> FileRepository:
    return FileRepository(db)


def get_llm_provider() -> LlmProvider:
    return GeminiLlmProvider(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
    )


def get_file_service(
    repository: FileRepository = Depends(get_file_repository),
    summary_provider: LlmProvider = Depends(get_llm_provider),
) -> FileService:
    return FileService(repository, summary_provider)
