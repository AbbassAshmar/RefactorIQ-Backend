import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID
from datetime import datetime
from time import perf_counter

from app.core.enums import ScanStatus
from app.scans.scans_service import ScanService
from app.github.services.github_service import GithubService
from app.scans.scans_dtos import ScanResponse
from app.analysis.services.scan_engine.pipeline.scan_workspace import ScanWorkspaceService
from app.users.users_service import UserService
from app.analysis.services.scan_engine.pipeline.scan_pipeline import ScanPipeline

import logging
logger = logging.getLogger(__name__)

class ScanEngineService:
    def __init__(
        self,
        scan_service: ScanService,
        github_service: GithubService,
        workspace_service: ScanWorkspaceService,
        scan_pipeline: ScanPipeline,
    ):
        self._scan_service = scan_service
        self._github_service = github_service
        self._workspace_service = workspace_service
        self._scan_pipeline = scan_pipeline

    def execute_scan(self, scan_id: UUID) -> None:
        started = perf_counter()
        logger.info("[SCAN ENGINE STARTED] scan_id=%s", scan_id)
        scan = self._scan_service.get_scan_by_id_include_project_user(scan_id)
        project = scan.project
        user = project.user
        access_token = GithubService._get_decrypted_access_token(user.github_access_token)

        # A worker termination or cancellation can leave a stale workspace;
        # clear it before creating the workspace for this execution.
        self._workspace_service.delete_by_scan_id(scan_id)
        workspace = self._workspace_service.create(scan_id)
        try:
            logger.info(
                "[SCAN CLONE STARTED] scan_id=%s project_id=%s repo=%s/%s branch=%s",
                scan_id,
                project.id,
                project.repo_owner,
                project.repo_name,
                project.branch,
            )
            self._github_service.clone_repository(
                repo_owner=project.repo_owner,
                repo_name=project.repo_name,
                branch=project.branch,
                access_token=access_token,
                destination=workspace.root_path,
            )
            logger.info("[SCAN CLONE COMPLETED] scan_id=%s", scan_id)

            self._run_tests_with_coverage(workspace.root_path)

            file_paths = workspace.python_files()
            logger.info("[SCAN FILE DISCOVERY COMPLETED] scan_id=%s file_count=%d", scan_id, len(file_paths))

            logger.info("[SCAN PIPELINE STARTED] scan_id=%s file_count=%d", scan_id, len(file_paths))
            self._scan_pipeline.run(
                file_paths,
                repo_root=workspace.root_path,
                scan_id=scan_id,
            )
            logger.info(
                "[SCAN ENGINE COMPLETED] scan_id=%s elapsed_seconds=%.3f",
                scan_id,
                perf_counter() - started,
            )
        finally:
            logger.info("[SCAN CLEANUP STARTED] scan_id=%s", scan_id)
            try:
                self._workspace_service.delete(workspace)
                logger.info("[SCAN CLEANUP COMPLETED] scan_id=%s", scan_id)
            except Exception:
                logger.exception(
                    "[SCAN CLEANUP FAILED] scan_id=%s",
                    scan_id,
                )

    def _run_tests_with_coverage(self, repo_root: Path) -> None:
        if not self._has_tests(repo_root):
            logger.info("[SCAN] No tests found in %s; coverage metric will be 0.0", repo_root)
            return

        env = os.environ.copy()
        source_path = str(repo_root / "src")
        env["PYTHONPATH"] = (
            source_path
            if not env.get("PYTHONPATH")
            else f"{source_path}{os.pathsep}{env['PYTHONPATH']}"
        )

        command = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--data-file",
            str(repo_root / ".coverage"),
            "-m",
            "pytest",
        ]
        logger.info("[SCAN] Running tests with coverage in %s", repo_root)
        try:
            result = subprocess.run(
                command,
                cwd=repo_root,
                env=env,
                text=True,
                capture_output=True,
                timeout=180,
                check=False,
            )
        except Exception as exc:
            logger.warning("[SCAN COVERAGE FAILED] repo_root=%s error=%s", repo_root, str(exc))
            return

        if result.returncode != 0:
            logger.warning(
                "[SCAN COVERAGE COMPLETED WITH FAILURES] repo_root=%s exit_code=%s",
                repo_root,
                result.returncode,
            )
            return

        logger.info("[SCAN COVERAGE COMPLETED] repo_root=%s", repo_root)

    def _has_tests(self, repo_root: Path) -> bool:
        test_dirs = [repo_root / "tests", repo_root / "test"]
        if any(path.is_dir() for path in test_dirs):
            return True
        return any(repo_root.rglob("test_*.py")) or any(repo_root.rglob("*_test.py"))
