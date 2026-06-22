from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path

import pytest

from app.analysis.services.scan_engine.pipeline.layers.history_analysis_layer import HistoryAnalysisLayer


def test_history_layer_counts_commits_contributors_bug_fixes_and_recent_split(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    target = repo / "src" / "target.py"
    peer = repo / "src" / "peer.py"
    target.parent.mkdir()

    target.write_text("def compute(value):\n    return value + 1\n", encoding="utf-8")
    _commit(repo, "initial target", author="old@example.test", date="2000-01-01T00:00:00+00:00")

    target.write_text(
        "def compute(value):\n"
        "    if value > 10:\n"
        "        return value + 2\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    peer.write_text("PEER = True\n", encoding="utf-8")
    _commit(repo, "fix branching bug", author="new@example.test")

    vector = HistoryAnalysisLayer().run(target)

    assert _non_complexity_errors(vector.errors) == []
    assert vector.metrics["contributors_count"] == 2
    assert vector.metrics["update_count"] == 2
    assert vector.metrics["recent_update_count"] == 1
    assert vector.metrics["historical_update_count"] == 1
    assert vector.metrics["recent_to_lifetime_update_ratio"] == 0.5
    assert vector.metrics["bug_fix_commit_count"] == 1
    assert vector.metrics["bug_fix_ratio"] == 0.5
    assert vector.metrics["co_change_file_count"] == 1
    assert vector.metadata["co_changed_files_sample"] == ["src/peer.py"]


def test_history_layer_computes_churn_and_churn_to_size_ratio(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    target = repo / "target.py"
    target.write_text("A = 1\nB = 2\nC = 3\n", encoding="utf-8")
    _commit(repo, "add target")

    vector = HistoryAnalysisLayer().run(target)

    assert _non_complexity_errors(vector.errors) == []
    assert vector.metrics["churn_rate"] == 3
    assert vector.metrics["churn_to_size_ratio"] == 1.0


def test_history_layer_caps_co_change_commit_scan_at_100(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    target = repo / "target.py"
    target.write_text("VALUE = 0\n", encoding="utf-8")
    _commit(repo, "add target")

    for index in range(105):
        target.write_text(f"VALUE = {index + 1}\n", encoding="utf-8")
        (repo / f"peer_{index}.py").write_text(f"PEER = {index}\n", encoding="utf-8")
        _commit(repo, f"change target with peer {index}")

    vector = HistoryAnalysisLayer().run(target)

    assert _non_complexity_errors(vector.errors) == []
    assert vector.metadata["co_change_commits_analyzed"] == 100
    assert vector.metrics["co_change_file_count"] == 100
    assert "target.py" not in vector.metadata["co_changed_files_sample"]


def test_history_layer_computes_cyclomatic_complexity_growth(tmp_path: Path) -> None:
    pytest.importorskip("radon")
    repo = _init_repo(tmp_path)
    target = repo / "target.py"
    target.write_text("def compute(value):\n    return value + 1\n", encoding="utf-8")
    _commit(repo, "add simple target", date="2000-01-01T00:00:00+00:00")

    target.write_text(
        "def compute(value):\n"
        "    if value > 10:\n"
        "        return value + 2\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    _commit(repo, "increase complexity")

    vector = HistoryAnalysisLayer().run(target)

    assert vector.errors == []
    assert vector.metrics["cyclomatic_complexity_growth_rate"] == 1.0


def test_history_layer_returns_safe_defaults_for_non_git_file(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("print('not tracked')\n", encoding="utf-8")

    vector = HistoryAnalysisLayer().run(target)

    assert vector.has_errors()
    assert vector.metrics == {
        "contributors_count": 0,
        "update_count": 0,
        "recent_update_count": 0,
        "historical_update_count": 0,
        "recent_to_lifetime_update_ratio": 0.0,
        "churn_rate": 0,
        "churn_to_size_ratio": 0.0,
        "bug_fix_commit_count": 0,
        "bug_fix_ratio": 0.0,
        "cyclomatic_complexity_growth_rate": 0.0,
        "co_change_file_count": 0,
    }


def _init_repo(path: Path) -> Path:
    _git(path, "init")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.test")
    return path


def _commit(
    repo: Path,
    message: str,
    *,
    author: str = "test@example.test",
    date: str | None = None,
) -> None:
    timestamp = date or datetime.now(timezone.utc).isoformat()
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": author.split("@")[0],
            "GIT_AUTHOR_EMAIL": author,
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_NAME": author.split("@")[0],
            "GIT_COMMITTER_EMAIL": author,
            "GIT_COMMITTER_DATE": timestamp,
        }
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message, env=env)


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        shell=False,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout


def _non_complexity_errors(errors: list[str]) -> list[str]:
    if find_spec("radon") is not None:
        return errors
    return [error for error in errors if not error.startswith("cyclomatic_complexity_growth_rate failed")]
