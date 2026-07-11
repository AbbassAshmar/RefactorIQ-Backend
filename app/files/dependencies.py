from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.core.database import get_db
from app.files.repository import FileRepository
from app.files.service import FileService
from app.files.summary_provider import FileSummaryProvider, GeminiFileSummaryProvider


def get_file_repository(db: Session = Depends(get_db)) -> FileRepository:
    return FileRepository(db)


def get_file_summary_provider() -> FileSummaryProvider:
    return GeminiFileSummaryProvider(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
        api_base_url=settings.GEMINI_API_BASE_URL,
        timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
    )


def get_file_service(
    repository: FileRepository = Depends(get_file_repository),
    summary_provider: FileSummaryProvider = Depends(get_file_summary_provider),
) -> FileService:
    return FileService(repository, summary_provider)
