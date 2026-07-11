from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.enums import ScanStatus
from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.models import Project, Scan, ScanFile
from app.overview.dtos import OverviewFileRow, OverviewScanScoreRow


class OverviewRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _scan_scope(self, user_id: uuid.UUID, scan_id: uuid.UUID) -> Scan:
        try:
            statement = (
                select(Scan)
                .join(Project, Scan.project_id == Project.id)
                .where(
                    Scan.id == scan_id,
                    Project.user_id == user_id,
                    Scan.status == ScanStatus.SUCCEEDED,
                )
            )
            scan = self._db.execute(statement).scalar_one_or_none()
            if scan is None:
                raise RecordNotFoundException(
                    "Successful scan not found",
                    details={"scan_id": str(scan_id)},
                )
            return scan
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to load overview scan",
                details={"scan_id": str(scan_id)},
            ) from exc

    def list_risk_trend_scans(
        self,
        user_id: uuid.UUID,
        scan_id: uuid.UUID,
        previous_count: int,
    ) -> list[OverviewScanScoreRow]:
        target = self._scan_scope(user_id, scan_id)
        try:
            target_score = self._average_score_statement(
                user_id=user_id,
                project_id=target.project_id,
                scan_ids=[target.id],
            )
            if target.finished_at is None:
                return [
                    OverviewScanScoreRow(
                        scan_id=target.id,
                        finished_at=None,
                        average_refactor_score=target_score,
                    )
                ]
            prior_statement = (
                select(
                    Scan.id,
                    Scan.finished_at,
                    func.coalesce(func.avg(ScanFile.refactor_score), 0.0),
                )
                .join(Project, Scan.project_id == Project.id)
                .outerjoin(ScanFile, ScanFile.scan_id == Scan.id)
                .where(
                    Project.user_id == user_id,
                    Scan.project_id == target.project_id,
                    Scan.status == ScanStatus.SUCCEEDED,
                    Scan.finished_at.is_not(None),
                    or_(
                        Scan.finished_at < target.finished_at,
                        (Scan.finished_at == target.finished_at) & (Scan.id < target.id),
                    ),
                )
                .group_by(Scan.id, Scan.finished_at)
                .order_by(Scan.finished_at.desc(), Scan.id.desc())
                .limit(previous_count)
            )
            prior_rows = self._db.execute(prior_statement).all()
            rows = [
                OverviewScanScoreRow(
                    scan_id=target.id,
                    finished_at=target.finished_at,
                    average_refactor_score=target_score,
                )
            ]
            rows.extend(
                OverviewScanScoreRow(
                    scan_id=row[0],
                    finished_at=row[1],
                    average_refactor_score=float(row[2] or 0.0),
                )
                for row in prior_rows
            )
            return sorted(
                rows,
                key=lambda row: (row.finished_at is not None, row.finished_at),
            )
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to build risk trend",
                details={"scan_id": str(scan_id)},
            ) from exc

    def _average_score_statement(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        scan_ids: Sequence[uuid.UUID],
    ) -> float:
        statement = (
            select(func.coalesce(func.avg(ScanFile.refactor_score), 0.0))
            .select_from(ScanFile)
            .join(Scan, ScanFile.scan_id == Scan.id)
            .join(Project, Scan.project_id == Project.id)
            .where(
                Project.user_id == user_id,
                Scan.project_id == project_id,
                Scan.id.in_(scan_ids),
            )
        )
        return float(self._db.execute(statement).scalar_one() or 0.0)

    def get_priority_band_counts(
        self,
        user_id: uuid.UUID,
        scan_id: uuid.UUID,
    ) -> dict[str, int]:
        self._scan_scope(user_id, scan_id)
        try:
            statement = (
                select(ScanFile.priority_band, func.count(ScanFile.id))
                .join(Scan, ScanFile.scan_id == Scan.id)
                .join(Project, Scan.project_id == Project.id)
                .where(Scan.id == scan_id, Project.user_id == user_id)
                .group_by(ScanFile.priority_band)
            )
            return {
                (str(row[0]).lower() if row[0] is not None else "unknown"): int(row[1])
                for row in self._db.execute(statement).all()
            }
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to aggregate scan priority bands",
                details={"scan_id": str(scan_id)},
            ) from exc

    def list_top_files(
        self,
        user_id: uuid.UUID,
        scan_id: uuid.UUID,
        limit: int,
    ) -> list[OverviewFileRow]:
        self._scan_scope(user_id, scan_id)
        try:
            null_order = case((ScanFile.refactor_score.is_(None), 1), else_=0)
            statement = (
                select(ScanFile)
                .join(Scan, ScanFile.scan_id == Scan.id)
                .join(Project, Scan.project_id == Project.id)
                .where(Scan.id == scan_id, Project.user_id == user_id)
                .order_by(null_order.asc(), ScanFile.refactor_score.desc(), ScanFile.file_path.asc())
                .limit(limit)
            )
            return [self._to_file_row(file) for file in self._db.execute(statement).scalars().all()]
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to list top refactor files",
                details={"scan_id": str(scan_id)},
            ) from exc

    def list_files_for_directory_risk(
        self,
        user_id: uuid.UUID,
        scan_id: uuid.UUID,
    ) -> list[OverviewFileRow]:
        self._scan_scope(user_id, scan_id)
        try:
            statement = (
                select(ScanFile)
                .join(Scan, ScanFile.scan_id == Scan.id)
                .join(Project, Scan.project_id == Project.id)
                .where(Scan.id == scan_id, Project.user_id == user_id)
                .order_by(ScanFile.file_path.asc())
            )
            return [self._to_file_row(file) for file in self._db.execute(statement).scalars().all()]
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to aggregate directory risk",
                details={"scan_id": str(scan_id)},
            ) from exc

    def _to_file_row(self, file: ScanFile) -> OverviewFileRow:
        return OverviewFileRow(
            id=file.id,
            file_path=file.file_path,
            refactor_score=float(file.refactor_score) if file.refactor_score is not None else None,
            priority_band=file.priority_band,
            metrics=file.metrics or {},
            metadata=file.metadata_json or {},
            errors=file.errors or {},
        )
