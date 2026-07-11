import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID
from datetime import datetime

from app.core.enums import ScanStatus
from app.scans.services.scan_service import ScanService
from app.github.services.service import GithubService
from app.schemas.scan import ScanResponse
from app.analysis.services.scan_engine.pipeline.scan_workspace import ScanWorkspaceService
from app.users.services.service import UserService
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

            self._run_tests_with_coverage(workspace.root_path)

            # log file paths found
            file_paths = workspace.python_files()
            logger.info(f"[SCAN] Found {len(file_paths)} Python files for scan {scan_id}")
            logger.info(f"[SCAN] Found {len(file_paths)} Python files for scan {scan_id}")

            self._scan_pipeline.run(
                file_paths,
                repo_root=workspace.root_path,
                scan_id=scan_id,
            )
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
            logger.warning("[SCAN] Failed to run coverage for %s: %s", repo_root, exc)
            return

        if result.returncode != 0:
            logger.warning(
                "[SCAN] Coverage test run failed for %s with exit code %s: %s",
                repo_root,
                result.returncode,
                (result.stderr or result.stdout)[-2000:],
            )
            return

        logger.info("[SCAN] Coverage data written to %s", repo_root / ".coverage")

    def _has_tests(self, repo_root: Path) -> bool:
        test_dirs = [repo_root / "tests", repo_root / "test"]
        if any(path.is_dir() for path in test_dirs):
            return True
        return any(repo_root.rglob("test_*.py")) or any(repo_root.rglob("*_test.py"))
