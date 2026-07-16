from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.projects.projects_repository import ProjectRepository
from app.projects.projects_service import ProjectService
from app.scans.dependencies import get_scan_service
from app.scans.scans_service import ScanService
from app.analysis.dependencies import get_scan_workspace_service
from app.analysis.services.scan_engine.pipeline.scan_workspace import ScanWorkspaceService


def get_project_repository(db: Session = Depends(get_db)) -> ProjectRepository:
    return ProjectRepository(db)


def get_project_service(
    project_repository: ProjectRepository = Depends(get_project_repository),
    scan_service: ScanService = Depends(get_scan_service),
    workspace_service: ScanWorkspaceService = Depends(get_scan_workspace_service),
) -> ProjectService:
    return ProjectService(project_repository, scan_service, workspace_service)
