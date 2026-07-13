from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.scan_visualization.scan_visualization_repository import ScanVisualizationRepository
from app.scan_visualization.scan_visualization_service import ScanVisualizationService


def get_scan_visualization_repository(
    db: Session = Depends(get_db),
) -> ScanVisualizationRepository:
    return ScanVisualizationRepository(db)


def get_scan_visualization_service(
    repository: ScanVisualizationRepository = Depends(get_scan_visualization_repository),
) -> ScanVisualizationService:
    return ScanVisualizationService(repository)
