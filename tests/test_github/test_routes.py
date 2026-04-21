from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.route_dependencies import get_current_payload
from app.github.dependencies import get_github_service
from app.schemas.auth import TokenPayload
from app.schemas.github import GithubBranchResponse, GithubRepositoryResponse


def test_get_repositories_unauthenticated(client: TestClient):
    response = client.get("/api/v1/github/repositories")
    assert response.status_code == 401


def test_get_branches_unauthenticated(client: TestClient):
    response = client.get("/api/v1/github/repositories/owner/repo/branches")
    assert response.status_code == 401


def test_get_repositories_and_branches_authenticated(client: TestClient):
    user_id = uuid.uuid4()
    github_service = AsyncMock()
    github_service.get_user_repositories.return_value = [
        GithubRepositoryResponse(
            name="RefactorIQ-frontend",
            owner="AbbassAshmar",
            full_name="AbbassAshmar/RefactorIQ-frontend",
            private=False,
            default_branch="main",
            html_url="https://github.com/AbbassAshmar/RefactorIQ-frontend",
        )
    ]
    github_service.get_repository_branches.return_value = [
        GithubBranchResponse(
            name="master",
            commit_sha="b0ddbff247a2d873d6b5907b979e48b4a853c67b",
            protected=False,
        )
    ]

    app = client.app
    app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub=str(user_id), role="client"
    )
    app.dependency_overrides[get_github_service] = lambda: github_service

    repositories_response = client.get("/api/v1/github/repositories")
    assert repositories_response.status_code == 200
    repositories_data = repositories_response.json()
    assert repositories_data["data"][0]["name"] == "RefactorIQ-frontend"
    assert repositories_data["data"][0]["owner"] == "AbbassAshmar"

    branches_response = client.get(
        "/api/v1/github/repositories/AbbassAshmar/Gollumia-Frontend/branches"
    )
    assert branches_response.status_code == 200
    branches_data = branches_response.json()
    assert branches_data["data"][0]["name"] == "master"
    assert (
        branches_data["data"][0]["commit_sha"]
        == "b0ddbff247a2d873d6b5907b979e48b4a853c67b"
    )

    app.dependency_overrides.pop(get_current_payload, None)
    app.dependency_overrides.pop(get_github_service, None)
