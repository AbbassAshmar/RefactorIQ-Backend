from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Depends
from sqlalchemy.orm import Session

from app.analysis.services.scan_engine.pipeline.scan_workspace import (
    ScanWorkspaceService,
)
from app.analysis.services.scan_engine.scan_engine import ScanEngineService
from app.config import settings
from app.core.database import SessionLocal
from app.dependencies import (
    build_role_repository,
    build_scans_queue_service,
    build_user_repository,
    build_user_service,
)
from app.github.dependencies import get_github_service
from app.github.services.client_service import GithubClientService
from app.github.services.service import GithubService
from app.scans.repositories.scan_repository import ScanRepository
from app.scans.services.scan_service import ScanService
from app.scans.dependencies import get_scan_service


def get_scan_workspace_service() -> ScanWorkspaceService:
    return build_scan_workspace_service()


def build_scan_workspace_service() -> ScanWorkspaceService:
    base_dir = settings.SCAN_REPO_BASE_DIR
    return ScanWorkspaceService(base_dir)


def get_scan_engine_service(
    scan_service: ScanService = Depends(get_scan_service),
    workspace_service: ScanWorkspaceService = Depends(get_scan_workspace_service),
    github_service: GithubService = Depends(get_github_service),
) -> ScanEngineService:
    return ScanEngineService(
        scan_service=scan_service,
        github_service=github_service, 
        workspace_service=workspace_service,
    )


def build_scan_engine_service(db: Session) -> ScanEngineService:
    scan_repository = ScanRepository(db)
    scan_queue_service = build_scans_queue_service()
    scan_service = ScanService(scan_repository, scan_queue_service)

    user_repository = build_user_repository(db)
    role_repository = build_role_repository(db)
    user_service = build_user_service(user_repository, role_repository)

    github_client = GithubClientService()
    github_service = GithubService(github_client, user_service)

    return ScanEngineService(
        scan_service=scan_service,
        github_service=github_service,
        workspace_service=build_scan_workspace_service(),
    )


@contextmanager
def provide_scan_engine_service() -> Iterator[ScanEngineService]:
    db = SessionLocal()
    try:
        yield build_scan_engine_service(db)
    finally:
        db.close()
