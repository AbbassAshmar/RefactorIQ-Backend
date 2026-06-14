from uuid import UUID
from datetime import datetime

from app.core.enums import ScanStatus
from app.scans.services.scan_service import ScanService
from app.github.services.service import GithubService
from app.schemas.scan import ScanResponse
from app.analysis.services.scan_engine.pipeline.scan_workspace import ScanWorkspaceService
from app.users.services.service import UserService

import logging
logger = logging.getLogger(__name__)

class ScanEngineService:
    def __init__(
        self,
        scan_service: ScanService,
        github_service: GithubService,
        workspace_service: ScanWorkspaceService,
    ):
        self._scan_service = scan_service
        self._github_service = github_service
        self._workspace_service = workspace_service

    def execute_scan(self, scan_id: UUID) -> None:
        scan = self._scan_service.get_scan_by_id_include_project_user(scan_id)
        project = scan.project
        user = project.user
        access_token = GithubService._get_decrypted_access_token(user.github_access_token)

        # Retries reuse the same scan_id, so clear any stale workspace first.
        self._workspace_service.delete_by_scan_id(scan_id)
        workspace = self._workspace_service.create(scan_id)
        try:
            logger.info(f"[SCAN] Cloning repository for scan {scan_id}")
            self._github_service.clone_repository(
                repo_owner=project.repo_owner,
                repo_name=project.repo_name,
                branch=project.branch,
                access_token=access_token,
                destination=workspace.root_path,
            )
            # layer 1 ... layer N (workspace passed down)
        finally:
            logger.info(f"[SCAN] Cleaning up workspace for scan {scan_id}")
            try:
                self._workspace_service.delete(workspace)
            except Exception:
                logger.warning(
                    "[SCAN] Failed to clean up workspace for scan %s",
                    scan_id,
                    exc_info=True,
                )
