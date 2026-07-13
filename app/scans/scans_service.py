from __future__ import annotations

import logging
import uuid
from datetime import datetime, time, timedelta, timezone

from app.core.exceptions.domain_exceptions import EntityNotFoundError, PersistenceError
from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.scans.scans_repository import ScanRepository
from app.queues.scans_queue_service import ScansQueueService
from app.scans.scans_dtos import (
    AdminScanListFilters,
    AdminScanListResult,
    AdminScanOwner,
    AdminScanProject,
    AdminScanResponse,
    FailedScanProject,
    FailedScanResponse,
    FailedScanUser,
    ScanListFilters,
    ScanListResult,
    ScanProjectUserResponse,
    ScanResponse,
    ScanStatusCount,
    ScanStatusDistributionResponse,
    ScanTimelinePoint,
    ScanTimelineResponse,
)
from app.core.enums import ScanStatus


logger = logging.getLogger(__name__)

    
class ScanService:
    def __init__(
        self,
        scan_repository: ScanRepository,
        scan_queue_service: ScansQueueService
    ):
        self.scan_repository = scan_repository
        self.scan_queue_service = scan_queue_service

    def create_and_enqueue_scan(self, project_id: uuid.UUID) -> ScanResponse:
        try:
            scan = self.scan_repository.create_scan(project_id)
            task_result = self.scan_queue_service.enqueue_scan(scan.id)
            logger.info(
                "Enqueued scan task %s for scan %s on queue scans",
                task_result.id,
                scan.id,
            )
            return scan
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to create scan") from exc

    def list_scans(self, filters: ScanListFilters) -> ScanListResult:
        try:
            if filters.project_id is not None and not self.scan_repository.project_belongs_to_user(
                project_id=filters.project_id,
                user_id=filters.user_id,
            ):
                raise EntityNotFoundError("project", filters.project_id)
            return self.scan_repository.list_scans(filters)
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list scans") from exc

    def list_admin_scans(
        self,
        filters: AdminScanListFilters,
    ) -> AdminScanListResult:
        try:
            rows, total_count = self.scan_repository.list_admin_scans(filters)
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list administrative scans") from exc
        return AdminScanListResult(
            items=[
                AdminScanResponse(
                    id=row.id,
                    status=row.status,
                    error_message=row.error_message,
                    created_at=row.created_at,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                    project=AdminScanProject(id=row.project_id, name=row.project_name),
                    owner=AdminScanOwner(
                        id=row.owner_id,
                        username=row.owner_username,
                        email=row.owner_email,
                    ),
                )
                for row in rows
            ],
            total_count=total_count,
        )

    def update_scan_status(
        self,
        scan_id: uuid.UUID,
        status: ScanStatus,
        error_message: str | None = None,
    ) -> ScanResponse:
        try:
            return self.scan_repository.update_scan_status(
                scan_id,
                status,
                error_message=error_message,
            )
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("scan", scan_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to update scan status") from exc
    
    def get_scan_by_id(self, scan_id: uuid.UUID) -> ScanResponse:
        try: 
            scan = self.scan_repository.get_scan_by_id(scan_id)
            return scan
        except RecordNotFoundException as exc:
            logger.warning("Scan with id %s not found", scan_id)
            raise EntityNotFoundError("scan", scan_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to retrieve scan") from exc
        
    def get_scan_by_id_include_project_user(self, scan_id: uuid.UUID) -> ScanProjectUserResponse:
        try: 
            scan = self.scan_repository.get_scan_by_id_include_project_user(scan_id)
            return scan
        except RecordNotFoundException as exc:
            logger.warning("Scan with id %s not found", scan_id)
            raise EntityNotFoundError("scan", scan_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to retrieve scan") from exc

    def get_scans_over_time(
        self,
        *,
        now: datetime | None = None,
        project_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> ScanTimelineResponse:
        if user_id is not None and project_id is not None:
            try:
                owns_project = self.scan_repository.project_belongs_to_user(
                    project_id=project_id,
                    user_id=user_id,
                )
            except DatabaseOperationException as exc:
                raise PersistenceError("Unable to validate scan project") from exc
            if not owns_project:
                raise EntityNotFoundError("project", project_id)

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        else:
            current = current.astimezone(timezone.utc)
        end_day = current.date()
        start_day = end_day - timedelta(days=13)
        created_from = datetime.combine(start_day, time.min, tzinfo=timezone.utc)
        created_before = datetime.combine(
            end_day + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
        try:
            counts = self.scan_repository.count_scans_by_day(
                created_from=created_from,
                created_before=created_before,
                project_id=project_id,
                user_id=user_id,
            )
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to load scans over time") from exc

        return ScanTimelineResponse(
            points=[
                ScanTimelinePoint(
                    date=start_day + timedelta(days=offset),
                    count=counts.get(start_day + timedelta(days=offset), 0),
                )
                for offset in range(14)
            ]
        )

    def get_scan_status_distribution(self) -> ScanStatusDistributionResponse:
        try:
            counts = self.scan_repository.get_status_distribution()
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to load scan status distribution") from exc
        return ScanStatusDistributionResponse(
            statuses=[
                ScanStatusCount(status=status, count=counts.get(status, 0))
                for status in ScanStatus
            ]
        )

    def list_failed_scans(self, *, limit: int) -> list[FailedScanResponse]:
        try:
            rows = self.scan_repository.list_failed_scans(limit=limit)
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list failed scans") from exc
        return [
            FailedScanResponse(
                id=row.id,
                status=row.status,
                error_message=row.error_message,
                created_at=row.created_at,
                started_at=row.started_at,
                finished_at=row.finished_at,
                project=FailedScanProject(id=row.project_id, name=row.project_name),
                user=FailedScanUser(id=row.user_id, username=row.username),
            )
            for row in rows
        ]

