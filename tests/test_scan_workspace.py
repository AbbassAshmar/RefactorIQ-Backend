import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app.analysis.services.scan_engine.pipeline.scan_workspace import (
    ScanWorkspaceService,
)


class ScanWorkspaceServiceTests(unittest.TestCase):
    def test_create_accepts_string_base_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ScanWorkspaceService(temp_dir)
            scan_id = uuid4()

            workspace = service.create(scan_id)

            self.assertEqual(workspace.scan_id, scan_id)
            self.assertEqual(workspace.root_path, Path(temp_dir) / str(scan_id))
            self.assertTrue(workspace.root_path.exists())

    def test_delete_by_scan_id_removes_stale_workspace_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ScanWorkspaceService(temp_dir)
            scan_id = uuid4()

            first_workspace = service.create(scan_id)
            self.assertTrue(first_workspace.root_path.exists())

            service.delete_by_scan_id(scan_id)
            self.assertFalse(first_workspace.root_path.exists())

            recreated_workspace = service.create(scan_id)
            self.assertTrue(recreated_workspace.root_path.exists())
