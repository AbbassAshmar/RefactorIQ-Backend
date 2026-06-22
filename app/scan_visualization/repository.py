from __future__ import annotations

import os
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector
from app.core.exceptions.repository_exceptions import DatabaseOperationException
from app.models import ScanVisualizationRecord
from app.scan_visualization.schemas import (
    ScanVisualizationRunSummary,
    ScanVisualizationVector,
)


class ScanVisualizationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _to_vector(record: ScanVisualizationRecord) -> ScanVisualizationVector:
        return ScanVisualizationVector(
            id=record.id,
            scan_id=record.scan_id,
            layer=record.layer,
            file_path=record.file_path,
            metrics=record.metrics or {},
            errors=record.errors or [],
            metadata=record.metadata_json or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def clear_scan(self, scan_id: uuid.UUID) -> None:
        try:
            self._db.execute(
                delete(ScanVisualizationRecord).where(
                    ScanVisualizationRecord.scan_id == scan_id
                )
            )
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to clear scan visualization records",
                details={"scan_id": str(scan_id)},
            ) from exc

    def store_vectors(
        self,
        scan_id: uuid.UUID,
        vectors: list[MetricsVector],
    ) -> list[ScanVisualizationVector]:
        records = [
            ScanVisualizationRecord(
                scan_id=scan_id,
                layer=vector.layer,
                file_path=str(vector.file_path) if vector.file_path is not None else None,
                metrics=self._json_safe(vector.metrics),
                errors=self._json_safe(vector.errors),
                metadata_json=self._json_safe(vector.metadata),
            )
            for vector in vectors
        ]

        try:
            self._db.add_all(records)
            self._db.commit()
            for record in records:
                self._db.refresh(record)
            return [self._to_vector(record) for record in records]
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to store scan visualization records",
                details={"scan_id": str(scan_id), "vector_count": len(vectors)},
            ) from exc

    def list_runs(self, limit: int = 25) -> list[ScanVisualizationRunSummary]:
        try:
            stmt = (
                select(
                    ScanVisualizationRecord.scan_id,
                    func.count(ScanVisualizationRecord.id),
                    func.count(distinct(ScanVisualizationRecord.file_path)),
                    func.max(ScanVisualizationRecord.created_at),
                )
                .where(ScanVisualizationRecord.scan_id.is_not(None))
                .group_by(ScanVisualizationRecord.scan_id)
                .order_by(func.max(ScanVisualizationRecord.created_at).desc())
                .limit(limit)
            )
            rows = self._db.execute(stmt).all()
            return [
                ScanVisualizationRunSummary(
                    scan_id=row[0],
                    vector_count=row[1],
                    file_count=row[2],
                    captured_at=row[3],
                )
                for row in rows
            ]
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to list scan visualization runs") from exc

    def latest_scan_id(self) -> uuid.UUID | None:
        try:
            stmt = (
                select(ScanVisualizationRecord.scan_id)
                .where(ScanVisualizationRecord.scan_id.is_not(None))
                .order_by(ScanVisualizationRecord.created_at.desc())
                .limit(1)
            )
            return self._db.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to load latest scan visualization run") from exc

    def list_by_scan_id(self, scan_id: uuid.UUID) -> list[ScanVisualizationVector]:
        try:
            stmt = (
                select(ScanVisualizationRecord)
                .where(ScanVisualizationRecord.scan_id == scan_id)
                .order_by(
                    ScanVisualizationRecord.file_path.asc(),
                    ScanVisualizationRecord.layer.asc(),
                    ScanVisualizationRecord.created_at.asc(),
                )
            )
            records = self._db.execute(stmt).scalars().all()
            return [self._to_vector(record) for record in records]
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to list scan visualization records",
                details={"scan_id": str(scan_id)},
            ) from exc

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, (Path, os.PathLike)):
            return str(value)
        if is_dataclass(value):
            return self._json_safe(asdict(value))
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        return value
