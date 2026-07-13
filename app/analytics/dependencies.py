"""Dependency wiring for administrative analytics."""

from fastapi import Depends

from app.analytics.analytics_service import AnalyticsService
from app.dependencies import get_user_repository
from app.projects.dependencies import get_project_repository
from app.projects.projects_repository import ProjectRepository
from app.scans.dependencies import get_scan_repository
from app.scans.scans_repository import ScanRepository
from app.users.repositories.user_repository import UserRepository


def get_analytics_service(
    user_repository: UserRepository = Depends(get_user_repository),
    scan_repository: ScanRepository = Depends(get_scan_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> AnalyticsService:
    return AnalyticsService(user_repository, scan_repository, project_repository)
