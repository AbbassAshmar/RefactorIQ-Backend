

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import NoResultFound, SQLAlchemyError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.models import Scan
from app.schemas.scan import ScanListFilters, ScanListResult, ScanProjectUserResponse, ScanResponse
from app.models.models import Project
from app.core.enums import ScanStatus

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
