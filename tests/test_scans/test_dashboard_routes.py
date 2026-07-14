from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.auth.auth_dtos import TokenPayload
from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.scans.dependencies import get_scan_service
from app.scans.scans_dtos import (
    ScanDurationTrendResponse,
    ScanRiskTrendResponse,
    ScanStatusCountsResponse,
)


def _authenticated(client: TestClient):
    user_id = uuid.uuid4()
    user_service = MagicMock()
    scan_service = MagicMock()
    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(sub=str(user_id), role="client")
    client.app.dependency_overrides[get_user_service] = lambda: user_service
    client.app.dependency_overrides[get_scan_service] = lambda: scan_service
    return user_id, scan_service


def test_dashboard_scan_routes_require_authentication(client: TestClient):
    project_id = uuid.uuid4()
    for path in (
        "/api/v1/scans/analytics/status-counts",
        "/api/v1/scans/analytics/risk-trend",
        "/api/v1/scans/analytics/duration-trend",
    ):
        assert client.get(path, params={"project_id": str(project_id)}).status_code == 401


def test_status_counts_route_returns_project_metadata(client: TestClient):
    user_id, service = _authenticated(client)
    project_id = uuid.uuid4()
    service.get_project_status_counts.return_value = ScanStatusCountsResponse(
        total=4, succeeded=2, pending=1, failed=1, running=0
    )

    response = client.get(
        "/api/v1/scans/analytics/status-counts",
        params={"project_id": str(project_id)},
    )

    assert response.status_code == 200
    assert response.json()["data"]["succeeded"] == 2
    assert response.json()["meta"]["project_id"] == str(project_id)
    service.get_project_status_counts.assert_called_once_with(user_id=user_id, project_id=project_id)


def test_trend_routes_return_series(client: TestClient):
    user_id, service = _authenticated(client)
    project_id = uuid.uuid4()
    service.get_project_risk_trend.return_value = ScanRiskTrendResponse(series=[])
    service.get_project_duration_trend.return_value = ScanDurationTrendResponse(series=[])

    assert client.get("/api/v1/scans/analytics/risk-trend", params={"project_id": str(project_id)}).status_code == 200
    assert client.get("/api/v1/scans/analytics/duration-trend", params={"project_id": str(project_id)}).status_code == 200
    service.get_project_risk_trend.assert_called_once_with(user_id=user_id, project_id=project_id)
    service.get_project_duration_trend.assert_called_once_with(user_id=user_id, project_id=project_id)
