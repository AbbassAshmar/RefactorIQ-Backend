from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.auth.auth_dtos import TokenPayload
from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.files.dependencies import get_file_service
from app.files.files_dtos import FilesAnalyzedTrendResponse, PriorityDistributionTrendResponse


def _authenticated(client: TestClient):
    user_id = uuid.uuid4()
    user_service = MagicMock()
    file_service = MagicMock()
    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(sub=str(user_id), role="client")
    client.app.dependency_overrides[get_user_service] = lambda: user_service
    client.app.dependency_overrides[get_file_service] = lambda: file_service
    return user_id, file_service


def test_dashboard_file_routes_require_authentication(client: TestClient):
    project_id = uuid.uuid4()
    for path in (
        "/api/v1/files/analytics/priority-distribution",
        "/api/v1/files/analytics/analyzed-trend",
    ):
        assert client.get(path, params={"project_id": str(project_id)}).status_code == 401


def test_dashboard_file_routes_return_project_scoped_data(client: TestClient):
    user_id, service = _authenticated(client)
    project_id = uuid.uuid4()
    service.get_project_priority_distribution.return_value = PriorityDistributionTrendResponse(series=[])
    service.get_project_files_analyzed.return_value = FilesAnalyzedTrendResponse(series=[])

    priority = client.get(
        "/api/v1/files/analytics/priority-distribution",
        params={"project_id": str(project_id)},
    )
    analyzed = client.get(
        "/api/v1/files/analytics/analyzed-trend",
        params={"project_id": str(project_id)},
    )

    assert priority.status_code == 200
    assert analyzed.status_code == 200
    assert priority.json()["meta"]["project_id"] == str(project_id)
    service.get_project_priority_distribution.assert_called_once_with(user_id=user_id, project_id=project_id)
    service.get_project_files_analyzed.assert_called_once_with(user_id=user_id, project_id=project_id)
