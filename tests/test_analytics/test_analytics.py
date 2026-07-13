from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.analytics.analytics_dtos import (
    AdminKpisResponse,
    KpiMetric,
    KpiPeriod,
    KpiPeriodWindow,
)
from app.analytics.analytics_service import AnalyticsService
from app.analytics.dependencies import get_analytics_service
from app.auth.auth_dtos import TokenPayload
from app.core.route_dependencies import get_current_payload


def test_kpis_use_rolling_windows_and_return_both_delta_forms():
    users = MagicMock()
    users.count_users.side_effect = [100, 12, 8]
    scans = MagicMock()
    scans.count_scans.side_effect = [250, 30, 20, 4, 3, 1]
    projects = MagicMock()
    projects.count_projects.side_effect = [60, 6, 0]
    service = AnalyticsService(users, scans, projects)
    now = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)

    result = service.get_kpis(now=now)

    assert result.period.current.end == now
    assert result.period.current.start == datetime(
        2026, 6, 13, 12, tzinfo=timezone.utc
    )
    assert result.kpis["users"].delta == 4
    assert result.kpis["users"].delta_percent == 50.0
    assert result.kpis["projects"].delta == 6
    assert result.kpis["projects"].delta_percent is None
    assert result.kpis["running_scans"].total == 4
    assert result.kpis["running_scans"].current_period_count == 3


def _kpi_response() -> AdminKpisResponse:
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    metric = KpiMetric(
        total=1,
        current_period_count=1,
        previous_period_count=0,
        delta=1,
        delta_percent=None,
    )
    return AdminKpisResponse(
        period=KpiPeriod(
            days=30,
            current=KpiPeriodWindow(start=now, end=now),
            previous=KpiPeriodWindow(start=now, end=now),
        ),
        kpis={
            "users": metric,
            "scans": metric,
            "projects": metric,
            "running_scans": metric,
        },
    )


def test_kpi_route_is_admin_only_and_returns_api_envelope(client: TestClient):
    service = MagicMock()
    service.get_kpis.return_value = _kpi_response()
    client.app.dependency_overrides[get_analytics_service] = lambda: service

    unauthenticated = client.get("/api/v1/admin/analytics/kpis")
    assert unauthenticated.status_code == 401

    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub="00000000-0000-0000-0000-000000000001",
        role="client",
    )
    forbidden = client.get("/api/v1/admin/analytics/kpis")
    assert forbidden.status_code == 403

    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub="00000000-0000-0000-0000-000000000001",
        role="admin",
    )
    response = client.get("/api/v1/admin/analytics/kpis")

    assert response.status_code == 200
    assert response.json()["data"]["kpis"]["users"]["total"] == 1
