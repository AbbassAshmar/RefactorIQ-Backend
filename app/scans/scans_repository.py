

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.models import Scan
from app.scans.scans_dtos import (
    AdminScanListFilters,
    AdminScanRow,
    FailedScanRow,
    ScanListFilters,
    ScanListResult,
    ScanProjectUserResponse,
    ScanResponse,
)
from app.models import ScanFile
from app.models.models import Project, User
from app.core.enums import ScanStatus

from logging import getLogger

logger = getLogger(__name__)

class ScanRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _to_response(scan: Scan) -> ScanResponse:
        return ScanResponse.model_validate(scan)
    
    @staticmethod
    def _to_response_include_project_user(scan: Scan) -> ScanProjectUserResponse:
        return ScanProjectUserResponse.model_validate(scan)

    def create_scan(self, project_id: uuid.UUID) -> ScanResponse:
        scan = Scan(project_id=project_id)
        try:
            self._db.add(scan)
            self._db.commit()
            self._db.refresh(scan)
            return self._to_response(scan)
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to create scan",
                details={
                    "project_id": str(project_id),
                },
            ) from exc
        
    def get_scan_by_id(self, scan_id: uuid.UUID) -> ScanResponse:
        try:
            scan = self._db.query(Scan).filter(Scan.id == scan_id).one()
            return self._to_response(scan)
        except NoResultFound:
            raise RecordNotFoundException(
                "Scan not found",
                details={"scan_id": str(scan_id)},
            )
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to retrieve scan",
                details={
                    "scan_id": str(scan_id),
                },
            ) from exc
        

    def get_scan_by_id_include_project_user(self, scan_id: uuid.UUID) -> ScanProjectUserResponse:
        try:
            scan = (
                self._db.query(Scan)
                .filter(Scan.id == scan_id)
                .options(
                    joinedload(Scan.project).joinedload(Project.user)
                )
                .one()
            )
            
            return self._to_response_include_project_user(scan)
        except NoResultFound:
            raise RecordNotFoundException(
                "Scan not found",
                details={"scan_id": str(scan_id)},
            )
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to retrieve scan with project and user",
                details={
                    "scan_id": str(scan_id),
                },
            ) from exc

    def update_scan_status(
        self,
        scan_id: uuid.UUID,
        status: ScanStatus,
        error_message: str | None = None,
    ) -> ScanResponse:
        try:
            scan = self._db.get(Scan, scan_id)
            if scan is None:
                raise RecordNotFoundException(
                    "Scan not found",
                    details={"scan_id": str(scan_id)},
                )

            now = datetime.now(timezone.utc)
            scan.status = status
            if status == ScanStatus.FAILED:
                scan.error_message = error_message
            else:
                scan.error_message = None
            if status == ScanStatus.RUNNING:
                scan.started_at = scan.started_at or now
                scan.finished_at = None
            elif status in {ScanStatus.SUCCEEDED, ScanStatus.FAILED, ScanStatus.CANCELLED}:
                scan.finished_at = now

            self._db.commit()
            self._db.refresh(scan)
            return self._to_response(scan)
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to update scan status",
                details={"scan_id": str(scan_id), "status": status.value},
            ) from exc

    def list_scans(self, filters: ScanListFilters) -> ScanListResult:
        try:
            conditions = [Project.user_id == filters.user_id]
            if filters.project_id is not None:
                conditions.append(Scan.project_id == filters.project_id)
            if filters.status is not None:
                conditions.append(Scan.status == filters.status)

            count_stmt = (
                select(func.count(Scan.id))
                .join(Project, Scan.project_id == Project.id)
                .where(*conditions)
            )
            total_count = self._db.execute(count_stmt).scalar_one()

            order_column = Scan.created_at.desc() if filters.sort_descending else Scan.created_at.asc()
            stmt = (
                select(Scan)
                .join(Project, Scan.project_id == Project.id)
                .where(*conditions)
                .order_by(order_column, Scan.id.desc())
                .offset((filters.page - 1) * filters.limit)
                .limit(filters.limit)
            )
            scans = self._db.execute(stmt).scalars().all()
            return ScanListResult(
                items=[self._to_response(scan) for scan in scans],
                total_count=total_count,
            )
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to list scans",
                details={
                    "user_id": str(filters.user_id),
                    "project_id": str(filters.project_id) if filters.project_id else None,
                    "status": filters.status,
                },
            ) from exc

    def project_belongs_to_user(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        try:
            statement = select(func.count(Project.id)).where(
                Project.id == project_id,
                Project.user_id == user_id,
            )
            return bool(self._db.execute(statement).scalar_one())
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to validate scan project ownership",
                details={
                    "project_id": str(project_id),
                    "user_id": str(user_id),
                },
            ) from exc

    def count_project_scans_by_status(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict[ScanStatus, int]:
        try:
            statement = (
                select(Scan.status, func.count(Scan.id))
                .join(Project, Scan.project_id == Project.id)
                .where(Project.id == project_id, Project.user_id == user_id)
                .group_by(Scan.status)
            )
            return {
                status if isinstance(status, ScanStatus) else ScanStatus(status): int(count)
                for status, count in self._db.execute(statement).all()
            }
        except (SQLAlchemyError, ValueError) as exc:
            logger.exception(
                "Failed to count project scan statuses user_id=%s project_id=%s",
                user_id,
                project_id,
            )
            raise DatabaseOperationException(
                "Failed to count project scan statuses",
                details={"project_id": str(project_id)},
            ) from exc

    def list_project_risk_trend(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        limit: int,
    ) -> list[tuple[uuid.UUID, datetime, float]]:
        try:
            statement = (
                select(
                    Scan.id,
                    Scan.finished_at,
                    func.coalesce(func.avg(ScanFile.refactor_score), 0.0),
                )
                .join(Project, Scan.project_id == Project.id)
                .outerjoin(ScanFile, ScanFile.scan_id == Scan.id)
                .where(
                    Project.id == project_id,
                    Project.user_id == user_id,
                    Scan.status == ScanStatus.SUCCEEDED,
                    Scan.finished_at.is_not(None),
                )
                .group_by(Scan.id, Scan.finished_at)
                .order_by(Scan.finished_at.desc(), Scan.id.desc())
                .limit(limit)
            )
            rows = self._db.execute(statement).all()
            return sorted(
                [(row[0], row[1], float(row[2] or 0.0)) for row in rows],
                key=lambda row: (row[1], row[0]),
            )
        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to build project risk trend user_id=%s project_id=%s",
                user_id,
                project_id,
            )
            raise DatabaseOperationException(
                "Failed to build project risk trend",
                details={"project_id": str(project_id)},
            ) from exc

    def list_project_scan_durations(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        limit: int,
    ) -> list[tuple[uuid.UUID, ScanStatus, datetime, datetime]]:
        try:
            statement = (
                select(Scan.id, Scan.status, Scan.started_at, Scan.finished_at)
                .join(Project, Scan.project_id == Project.id)
                .where(
                    Project.id == project_id,
                    Project.user_id == user_id,
                    Scan.status.in_(
                        [ScanStatus.SUCCEEDED, ScanStatus.FAILED, ScanStatus.CANCELLED]
                    ),
                    Scan.started_at.is_not(None),
                    Scan.finished_at.is_not(None),
                )
                .order_by(Scan.finished_at.desc(), Scan.id.desc())
                .limit(limit)
            )
            rows = self._db.execute(statement).all()
            return sorted(
                [(row[0], row[1], row[2], row[3]) for row in rows],
                key=lambda row: (row[3], row[0]),
            )
        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to build project duration trend user_id=%s project_id=%s",
                user_id,
                project_id,
            )
            raise DatabaseOperationException(
                "Failed to build project duration trend",
                details={"project_id": str(project_id)},
            ) from exc

    def list_admin_scans(
        self,
        filters: AdminScanListFilters,
    ) -> tuple[list[AdminScanRow], int]:
        try:
            conditions = []
            if filters.project_id is not None:
                conditions.append(Scan.project_id == filters.project_id)
            if filters.status is not None:
                conditions.append(Scan.status == filters.status)

            total_statement = select(func.count(Scan.id)).where(*conditions)
            total_count = int(self._db.execute(total_statement).scalar_one() or 0)

            order_column = (
                Scan.created_at.desc()
                if filters.sort_descending
                else Scan.created_at.asc()
            )
            statement = (
                select(
                    Scan.id,
                    Scan.status,
                    Scan.error_message,
                    Scan.created_at,
                    Scan.started_at,
                    Scan.finished_at,
                    Project.id,
                    Project.name,
                    User.id,
                    User.username,
                    User.email,
                )
                .join(Project, Scan.project_id == Project.id)
                .join(User, Project.user_id == User.id)
                .where(*conditions)
                .order_by(order_column, Scan.id.desc())
                .offset((filters.page - 1) * filters.limit)
                .limit(filters.limit)
            )
            rows = self._db.execute(statement).all()
            return (
                [
                    AdminScanRow(
                        id=row[0],
                        status=row[1],
                        error_message=row[2],
                        created_at=row[3],
                        started_at=row[4],
                        finished_at=row[5],
                        project_id=row[6],
                        project_name=row[7],
                        owner_id=row[8],
                        owner_username=row[9],
                        owner_email=row[10],
                    )
                    for row in rows
                ],
                total_count,
            )
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to list administrative scans",
                details={
                    "project_id": str(filters.project_id) if filters.project_id else None,
                    "status": filters.status.value if filters.status else None,
                },
            ) from exc

    def count_scans(
        self,
        *,
        status: ScanStatus | None = None,
        created_from: datetime | None = None,
        created_before: datetime | None = None,
    ) -> int:
        """Count scans, optionally filtered by status and creation window."""
        try:
            statement = select(func.count(Scan.id))
            if status is not None:
                statement = statement.where(Scan.status == status)
            if created_from is not None:
                statement = statement.where(Scan.created_at >= created_from)
            if created_before is not None:
                statement = statement.where(Scan.created_at < created_before)
            return int(self._db.execute(statement).scalar_one() or 0)
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to count scans",
                details={"status": status.value if status else None},
            ) from exc

    def count_scans_by_day(
        self,
        *,
        created_from: datetime,
        created_before: datetime,
        project_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> dict[date, int]:
        """Count created scans by calendar day within a half-open window."""
        try:
            day = func.date(Scan.created_at)
            conditions = [
                Scan.created_at >= created_from,
                Scan.created_at < created_before,
            ]
            if project_id is not None:
                conditions.append(Scan.project_id == project_id)

            statement = select(day, func.count(Scan.id))
            if user_id is not None:
                statement = statement.join(Project, Scan.project_id == Project.id)
                conditions.append(Project.user_id == user_id)
            statement = statement.where(*conditions).group_by(day).order_by(day.asc())
            counts: dict[date, int] = {}
            for day_value, count in self._db.execute(statement).all():
                if isinstance(day_value, datetime):
                    normalized_day = day_value.date()
                elif isinstance(day_value, date):
                    normalized_day = day_value
                else:
                    normalized_day = date.fromisoformat(str(day_value))
                counts[normalized_day] = int(count)
            return counts
        except (SQLAlchemyError, ValueError) as exc:
            raise DatabaseOperationException(
                "Failed to aggregate scans over time"
            ) from exc

    def get_status_distribution(self) -> dict[ScanStatus, int]:
        try:
            statement = select(Scan.status, func.count(Scan.id)).group_by(Scan.status)
            rows = self._db.execute(statement).all()
            return {
                status if isinstance(status, ScanStatus) else ScanStatus(status): int(count)
                for status, count in rows
            }
        except (SQLAlchemyError, ValueError) as exc:
            raise DatabaseOperationException(
                "Failed to aggregate scan status distribution"
            ) from exc

    def list_failed_scans(self, *, limit: int) -> list[FailedScanRow]:
        try:
            failure_time = func.coalesce(
                Scan.finished_at,
                Scan.updated_at,
                Scan.created_at,
            )
            statement = (
                select(
                    Scan.id,
                    Scan.status,
                    Scan.error_message,
                    Scan.created_at,
                    Scan.started_at,
                    Scan.finished_at,
                    Project.id,
                    Project.name,
                    User.id,
                    User.username,
                )
                .join(Project, Scan.project_id == Project.id)
                .join(User, Project.user_id == User.id)
                .where(Scan.status == ScanStatus.FAILED)
                .order_by(failure_time.desc(), Scan.id.desc())
                .limit(limit)
            )
            return [
                FailedScanRow(
                    id=row[0],
                    status=row[1],
                    error_message=row[2],
                    created_at=row[3],
                    started_at=row[4],
                    finished_at=row[5],
                    project_id=row[6],
                    project_name=row[7],
                    user_id=row[8],
                    username=row[9],
                )
                for row in self._db.execute(statement).all()
            ]
        except SQLAlchemyError as exc:
            logger.exception("Failed to list failed scans", exc_info=exc)
            raise DatabaseOperationException("Failed to list failed scans") from exc
