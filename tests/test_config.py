import os
import unittest
from pathlib import Path

from app.core.path_utils import resolve_scan_repo_base_dir


BASE_DIR = Path(__file__).resolve().parents[1]


class SettingsPathResolutionTests(unittest.TestCase):
    def test_relative_scan_repo_base_dir_resolves_against_backend_root(self) -> None:
        resolved = resolve_scan_repo_base_dir("workspace", base_dir=BASE_DIR)

        self.assertEqual(resolved, (BASE_DIR / "workspace").resolve())

    @unittest.skipIf(os.name == "nt", "POSIX absolute path behavior only applies on non-Windows")
    def test_absolute_posix_path_remains_unchanged(self) -> None:
        path = Path("/backend/workspace")

        resolved = resolve_scan_repo_base_dir(path, base_dir=BASE_DIR)

        self.assertEqual(resolved, path.resolve())

    @unittest.skipUnless(os.name == "nt", "Windows absolute path behavior requires Windows")
    def test_absolute_windows_path_remains_unchanged_on_windows(self) -> None:
        path = Path(r"C:\Users\srour\Documents\Vs code\RefactorIQ\backend\workspace")

        resolved = resolve_scan_repo_base_dir(path, base_dir=BASE_DIR)

        self.assertEqual(resolved, path.resolve())

    def test_windows_style_path_raises_on_non_windows(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "backend-relative path like 'workspace'",
        ):
            resolve_scan_repo_base_dir(
                r"C:\Users\srour\Documents\Vs code\RefactorIQ\backend\workspace",
                base_dir=BASE_DIR,
                running_on_windows=False,
            )
