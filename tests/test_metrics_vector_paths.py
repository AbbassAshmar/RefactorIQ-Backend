from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector


def test_per_file_vectors_require_both_paths_and_canonicalize_relative_identity() -> None:
    vector = MetricsVector(
        layer="static_analysis",
        absolute_path=Path("C:/scan-1/repository/app/main.py"),
        relative_path=r"app\main.py",
    )

    assert vector.relative_path == "app/main.py"
    assert vector.absolute_path is not None

    with pytest.raises(ValueError, match="both be set"):
        MetricsVector(layer="static_analysis", absolute_path=Path("C:/scan-1/repository/app/main.py"))

    with pytest.raises(ValueError, match="both be set"):
        MetricsVector(layer="static_analysis", relative_path="app/main.py")


@pytest.mark.parametrize("relative_path", ["/app/main.py", "app/../main.py", "./app/main.py", "", "C:/repo/app/main.py"])
def test_relative_path_rejects_noncanonical_or_nonrelative_values(relative_path: str) -> None:
    with pytest.raises(ValueError):
        MetricsVector(
            layer="static_analysis",
            absolute_path=Path("C:/scan-1/repository/app/main.py"),
            relative_path=relative_path,
        )


def test_summary_vectors_allow_no_file_paths() -> None:
    vector = MetricsVector(layer="decision_analysis")

    assert vector.absolute_path is None
    assert vector.relative_path is None


def test_relative_identity_is_stable_when_scan_workspaces_change() -> None:
    first = MetricsVector(
        layer="static_analysis",
        absolute_path=Path("C:/scan-1/repository/app/main.py"),
        relative_path="app/main.py",
    )
    second = MetricsVector(
        layer="static_analysis",
        absolute_path=Path("C:/scan-2/repository/app/main.py"),
        relative_path="app/main.py",
    )

    assert first.absolute_path != second.absolute_path
    assert first.relative_path == second.relative_path == "app/main.py"
