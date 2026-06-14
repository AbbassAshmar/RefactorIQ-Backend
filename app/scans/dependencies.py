


from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.scans.repositories.scan_repository import ScanRepository
from app.scans.services.scan_service import ScanService

from app.queues.scans_queue_service import ScansQueueService
from app.dependencies import get_scans_queue_service

def get_scan_repository(db: Session = Depends(get_db)) -> ScanRepository:
    return ScanRepository(db)

def get_scan_service(
    scan_repository: ScanRepository = Depends(get_scan_repository),
    scan_queue_service: ScansQueueService = Depends(get_scans_queue_service)
) -> ScanService:
    return ScanService(scan_repository, scan_queue_service)
