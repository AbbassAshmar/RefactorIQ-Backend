from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.auth.auth_dtos import TokenPayload
from app.core.enums import ScanStatus, UserRole
from app.core.route_dependencies import get_current_payload
from app.models import Project, Role, Scan, User
from app.scans.dependencies import get_scan_service
from app.scans.scans_dtos import (
    ScanStatusDistributionResponse,
    ScanTimelineResponse,
)
from app.scans.scans_repository import ScanRepository
from app.scans.scans_service import ScanService
from app.workers.scan_worker import on_scan_attempt_failed


def _scan_service(db_session) -> ScanService:
    return ScanService(ScanRepository(db_session), MagicMock())


def test_scan_analytics_zero_fill_statuses_and_failed_scan_details(db_session):
    role = Role(name=UserRole.CLIENT)
    user = User(email="analytics@example.com", username="analytics-owner", role=role)
    project = Project(
        name="Analytics Project",
        repo_owner="owner",
        repo_name="repo",
        branch="main",
        user=user,
    )
    now = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)
    succeeded = Scan(
        project=project,
        status=ScanStatus.SUCCEEDED,
        created_at=now - timedelta(days=2),
        started_at=now - timedelta(days=2, minutes=3),
        finished_at=now - timedelta(days=2),
    )
    failed = Scan(
        project=project,
        status=ScanStatus.FAILED,
        error_message="repository clone failed",
        created_at=now - timedelta(days=1),
        started_at=now - timedelta(days=1, minutes=2),
        finished_at=now - timedelta(days=1),
    )
    db_session.add_all([succeeded, failed])
    db_session.commit()

    service = _scan_service(db_session)
    timeline = service.get_scans_over_time(now=now)
    distribution = service.get_scan_status_distribution()
    failed_scans = service.list_failed_scans(limit=5)

    assert len(timeline.points) == 14
    assert timeline.points[-2].count == 1
    assert timeline.points[-3].count == 1
    assert timeline.points[0].count == 0
    status_counts = {item.status: item.count for item in distribution.statuses}
    assert status_counts == {
        ScanStatus.PENDING: 0,
        ScanStatus.RUNNING: 0,
        ScanStatus.SUCCEEDED: 1,
        ScanStatus.FAILED: 1,
        ScanStatus.CANCELLED: 0,
    }
    assert failed_scans[0].error_message == "repository clone failed"
    assert failed_scans[0].project.name == "Analytics Project"
    assert failed_scans[0].user.username == "analytics-owner"


def test_terminal_worker_failure_persists_message_but_retry_does_not():
    scan_id = __import__("uuid").uuid4()
    task = MagicMock()
    task.request.retries = 3
    task.max_retries = 3
    service = MagicMock()

    with patch(
        "app.workers.scan_worker.provide_scan_service",
        return_value=nullcontext(service),
    ):
        on_scan_attempt_failed(
            task,
            scan_id,
            RuntimeError("pipeline exploded"),
            is_terminal=True,
        )
    service.update_scan_status.assert_called_once_with(
        scan_id,
        ScanStatus.FAILED,
        error_message="pipeline exploded",
    )

    service.reset_mock()
    on_scan_attempt_failed(
        task,
        scan_id,
        RuntimeError("temporary"),
        is_terminal=False,
    )
    service.update_scan_status.assert_not_called()


def test_scan_status_transition_clears_stale_error(db_session):
    role = Role(name=UserRole.CLIENT)
    user = User(email="stale@example.com", username="stale", role=role)
    project = Project(
        name="Stale",
        repo_owner="owner",
        repo_name="repo",
        branch="main",
        user=user,
    )
    scan = Scan(project=project)
    db_session.add(scan)
    db_session.commit()

    repository = ScanRepository(db_session)
    repository.update_scan_status(
        scan.id,
        ScanStatus.FAILED,
        error_message="first failure",
    )
    db_session.refresh(scan)
    assert scan.error_message == "first failure"

    repository.update_scan_status(scan.id, ScanStatus.RUNNING)
    db_session.refresh(scan)
    assert scan.error_message is None


def test_scan_admin_routes_require_admin_and_validate_limit(client: TestClient):
    service = MagicMock()
    service.get_scans_over_time.return_value = ScanTimelineResponse(points=[])
    service.get_scan_status_distribution.return_value = (
        ScanStatusDistributionResponse(statuses=[])
    )
    service.list_failed_scans.return_value = []
    client.app.dependency_overrides[get_scan_service] = lambda: service

    assert client.get("/api/v1/admin/analytics/scans-over-time").status_code == 401

    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub="00000000-0000-0000-0000-000000000001",
        role="client",
    )
    assert (
        client.get("/api/v1/admin/analytics/scan-status-distribution").status_code
        == 403
    )

    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub="00000000-0000-0000-0000-000000000001",
        role="admin",
    )
    response = client.get("/api/v1/admin/analytics/failed-scans", params={"limit": 7})
    assert response.status_code == 200
    assert response.json()["data"]["scans"] == []
    service.list_failed_scans.assert_called_once_with(limit=7)
    assert (
        client.get("/api/v1/admin/analytics/failed-scans", params={"limit": 101}).status_code
        == 422
    )
