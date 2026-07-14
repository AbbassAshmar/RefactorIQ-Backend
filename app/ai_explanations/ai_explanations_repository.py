from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai_explanations.ai_explanations_dtos import AiExplanationRow, AiExplanationType
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
)
from app.models import AiExplanation


class AiExplanationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_for_file(
        self,
        file_id: uuid.UUID,
        explanation_type: AiExplanationType,
    ) -> AiExplanationRow | None:
        return self._get(file_id=file_id, scan_id=None, explanation_type=explanation_type)

    def get_for_scan(
        self,
        scan_id: uuid.UUID,
        explanation_type: AiExplanationType,
    ) -> AiExplanationRow | None:
        return self._get(file_id=None, scan_id=scan_id, explanation_type=explanation_type)

    def create_for_file(
        self,
        file_id: uuid.UUID,
        explanation_type: AiExplanationType,
        explanation: str,
    ) -> AiExplanationRow:
        return self._create(
            file_id=file_id,
            scan_id=None,
            explanation_type=explanation_type,
            explanation=explanation,
        )

    def create_for_scan(
        self,
        scan_id: uuid.UUID,
        explanation_type: AiExplanationType,
        explanation: str,
    ) -> AiExplanationRow:
        return self._create(
            file_id=None,
            scan_id=scan_id,
            explanation_type=explanation_type,
            explanation=explanation,
        )

    def _get(
        self,
        *,
        file_id: uuid.UUID | None,
        scan_id: uuid.UUID | None,
        explanation_type: AiExplanationType,
    ) -> AiExplanationRow | None:
        try:
            statement = select(AiExplanation).where(
                AiExplanation.type == explanation_type.value,
            )
            statement = statement.where(
                AiExplanation.file_id == file_id
                if file_id is not None
                else AiExplanation.scan_id == scan_id
            )
            record = self._db.execute(statement).scalar_one_or_none()
            return self._to_row(record) if record is not None else None
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to load AI explanation",
                details={
                    "type": explanation_type.value,
                    "file_id": str(file_id) if file_id else None,
                    "scan_id": str(scan_id) if scan_id else None,
                },
            ) from exc

    def _create(
        self,
        *,
        file_id: uuid.UUID | None,
        scan_id: uuid.UUID | None,
        explanation_type: AiExplanationType,
        explanation: str,
    ) -> AiExplanationRow:
        record = AiExplanation(
            file_id=file_id,
            scan_id=scan_id,
            type=explanation_type.value,
            explanation=explanation,
        )
        try:
            self._db.add(record)
            self._db.commit()
            self._db.refresh(record)
            return self._to_row(record)
        except IntegrityError as exc:
            self._db.rollback()
            existing = self._get(
                file_id=file_id,
                scan_id=scan_id,
                explanation_type=explanation_type,
            )
            if existing is not None:
                return existing
            raise DuplicateRecordException(
                "AI explanation already exists",
                details={"type": explanation_type.value},
            ) from exc
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to store AI explanation",
                details={
                    "type": explanation_type.value,
                    "file_id": str(file_id) if file_id else None,
                    "scan_id": str(scan_id) if scan_id else None,
                },
            ) from exc

    @staticmethod
    def _to_row(record: AiExplanation) -> AiExplanationRow:
        return AiExplanationRow(
            id=record.id,
            type=record.type,
            explanation=record.explanation,
            file_id=record.file_id,
            scan_id=record.scan_id,
        )
