from __future__ import annotations

import logging
import uuid

from app.core.exceptions.domain_exceptions import EntityNotFoundError, PersistenceError
from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.scans.scans_repository import ScanRepository
from app.queues.scans_queue_service import ScansQueueService
from app.scans.scans_dtos import ScanListFilters, ScanListResult, ScanResponse, ScanProjectUserResponse
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
            return self.scan_repository.list_scans(filters)
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list scans") from exc

    def update_scan_status(self, scan_id: uuid.UUID, status: ScanStatus) -> ScanResponse:
        try:
            return self.scan_repository.update_scan_status(scan_id, status)
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

