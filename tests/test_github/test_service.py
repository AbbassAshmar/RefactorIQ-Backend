from __future__ import annotations

import subprocess
from pathlib import Path

from app.github.services import service as github_service_module
from app.github.services.service import GithubService


def test_clone_repository_keeps_branch_but_does_not_use_shallow_depth(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured_command: list[str] = []

    def fake_run(command, **kwargs):
        captured_command.extend(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(github_service_module.subprocess, "run", fake_run)

    service = GithubService(github_client_service=None, user_service=None)
    service.clone_repository(
        repo_owner="owner",
        repo_name="repo",
        branch="main",
        access_token="token",
        destination=tmp_path / "repo",
    )

    assert captured_command[:2] == ["git", "clone"]
    assert "--branch" in captured_command
    assert "main" in captured_command
    assert "--single-branch" in captured_command
    assert "--depth" not in captured_command
    assert "1" not in captured_command
