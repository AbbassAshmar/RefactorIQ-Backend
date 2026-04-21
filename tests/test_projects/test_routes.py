from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.projects.dependencies import get_project_service
from app.schemas.auth import TokenPayload
from app.schemas.project import ProjectCreate, ProjectResponse


def test_create_project_unauthenticated(client: TestClient):
    response = client.post(
        "/api/v1/projects/",
        json={
            "name": "My Project",
            "repo_owner": "owner",
            "repo_name": "repo-name",
            "branch": "main",
        },
    )
    assert response.status_code == 401


def test_list_projects_unauthenticated(client: TestClient):
    response = client.get("/api/v1/projects/")
    assert response.status_code == 401


def test_create_and_list_projects_authenticated(client: TestClient):
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    created = ProjectResponse(
        id=uuid.uuid4(),
        user_id=user_id,
        name="My Project",
        repo_owner="owner",
        repo_name="repo-name",
        branch="main",
        created_at=now,
        updated_at=now,
    )

    user_service = MagicMock()
    user_service.get_user.return_value = MagicMock()

    project_service = MagicMock()
    project_service.create_project.return_value = created
    project_service.list_user_projects.return_value = [created]

    app = client.app
    app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub=str(user_id), role="client"
    )
    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_project_service] = lambda: project_service

    body = ProjectCreate(
        name="My Project",
        repo_owner="owner",
        repo_name="repo-name",
        branch="main",
    ).model_dump()

    create_response = client.post("/api/v1/projects/", json=body)
    assert create_response.status_code == 200
    create_data = create_response.json()
    assert create_data["data"]["name"] == "My Project"
    assert create_data["data"]["repo_owner"] == "owner"
    assert create_data["data"]["repo_name"] == "repo-name"
    assert create_data["data"]["branch"] == "main"

    list_response = client.get("/api/v1/projects/")
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert len(list_data["data"]) == 1
    assert list_data["data"][0]["name"] == "My Project"

    app.dependency_overrides.pop(get_current_payload, None)
    app.dependency_overrides.pop(get_user_service, None)
    app.dependency_overrides.pop(get_project_service, None)
