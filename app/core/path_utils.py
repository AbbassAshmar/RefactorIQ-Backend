from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath


def resolve_scan_repo_base_dir(
    value: Path | str,
    *,
    base_dir: Path,
    running_on_windows: bool | None = None,
) -> Path:
    if running_on_windows is None:
        running_on_windows = os.name == "nt"

    raw_value = os.fspath(value).strip()
    if not raw_value:
        raise ValueError("SCAN_REPO_BASE_DIR cannot be empty")

    if not running_on_windows and PureWindowsPath(raw_value).is_absolute():
        raise ValueError(
            "SCAN_REPO_BASE_DIR must use a backend-relative path like 'workspace' "
            "or a Linux absolute path like '/backend/workspace' when running on "
            "non-Windows environments."
        )

    path = Path(raw_value)
    if path.is_absolute():
        return path.resolve()

    return (base_dir / path).resolve()
