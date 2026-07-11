from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
import shutil

from app.analysis.services.scan_engine.pipeline.metrics_vector import validate_relative_path

import logging
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ScanWorkspace:
    scan_id: UUID
    root_path: Path

    def __post_init__(self):
        root = self.root_path.resolve()

        if not root.exists():
            raise ValueError(f"Workspace root does not exist: {root}")

        if not root.is_dir():
            raise ValueError(f"Workspace root is not a directory: {root}")

        object.__setattr__(self, "root_path", root)

    def python_files(self) -> list[Path]:
        logger.info(f"[WORKSPACE] Scanning for Python files in workspace {self.scan_id} at {self.root_path}")
        # self.root_path.rglob("*.py")
        logger.info(f"[WORKSPACE] Found {len(list(self.root_path.rglob('*.py')))} Python files in workspace {self.scan_id} before filtering")
        
        return [
            path
            for path in self.root_path.rglob("*.py")
            if self.is_valid_code_file(path)
        ]

    def relative_path(self, file_path: Path) -> str:
        file_path = file_path.resolve()
        self.ensure_inside_workspace(file_path)
        return validate_relative_path(file_path.relative_to(self.root_path).as_posix())

    def read_text(self, file_path: Path) -> str:
        file_path = file_path.resolve()
        self.ensure_inside_workspace(file_path)
        return file_path.read_text(encoding="utf-8")

    def ensure_inside_workspace(self, file_path: Path) -> None:
        try:
            file_path.relative_to(self.root_path)
        except ValueError:
            raise ValueError(
                f"File path is outside scan workspace: {file_path}"
            )

    def is_valid_code_file(self, file_path: Path) -> bool:
        ignored_parts = {
            ".git",
            "__pycache__",
            ".venv",
            "venv",
            "node_modules",
            ".mypy_cache",
            ".pytest_cache",
        }

        return not any(part in ignored_parts for part in file_path.parts)


# Service for creating repo directory and cleaning up after scan is done
class ScanWorkspaceService:
    def __init__(self, base_dir: Path | str) -> None:
        self._base_dir = Path(base_dir)

    def path_for(self, scan_id: UUID) -> Path:
        return self._base_dir / str(scan_id)

    def create(self, scan_id: UUID) -> ScanWorkspace:
        path = self.path_for(scan_id)
        path.mkdir(parents=True, exist_ok=False)
        return ScanWorkspace(scan_id=scan_id, root_path=path)

    def delete(self, workspace: ScanWorkspace) -> None:
        if workspace.root_path.exists():
            shutil.rmtree(workspace.root_path)

    def delete_by_scan_id(self, scan_id: UUID) -> None:
        path = self.path_for(scan_id)
        if path.exists():
            shutil.rmtree(path)
