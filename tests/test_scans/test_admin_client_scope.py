from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth.auth_dtos import TokenPayload
from app.core.enums import ScanStatus, UserRole
from app.core.exceptions.domain_exceptions import EntityNotFoundError
from app.core.route_dependencies import get_current_payload
from app.models import Project, Role, Scan, User
from app.scans.dependencies import get_scan_service
from app.scans.scans_dtos import (
    AdminScanListFilters,
    AdminScanListResult,
    ScanListFilters,
    ScanTimelineResponse,
)
from app.scans.scans_repository import ScanRepository
from app.scans.scans_service import ScanService


def test_client_scan_reads_are_owner_scoped_and_foreign_project_fails(db_session):
    role = Role(name=UserRole.CLIENT)
    owner = User(email="owner-scope@example.com", username="owner", role=role)
    other = User(email="other-scope@example.com", username="other", role=role)
    owner_project = Project(
        name="Owner project",
        repo_owner="owner",
        repo_name="owned",
        branch="main",
        user=owner,
    )
    other_project = Project(
        name="Other project",
        repo_owner="other",
        repo_name="foreign",
        branch="main",
        user=other,
    )
    now = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)
    owner_scan = Scan(project=owner_project, created_at=now - timedelta(days=1))
    other_scan = Scan(project=other_project, created_at=now - timedelta(days=1))
    db_session.add_all([owner_scan, other_scan])
    db_session.commit()

    service = ScanService(ScanRepository(db_session), MagicMock())
    own_result = service.list_scans(ScanListFilters(user_id=owner.id))
    own_timeline = service.get_scans_over_time(user_id=owner.id, now=now)

    assert own_result.total_count == 1
    assert own_result.items[0].id == owner_scan.id
    assert own_timeline.points[-2].count == 1

    with pytest.raises(EntityNotFoundError):
        service.list_scans(
            ScanListFilters(user_id=owner.id, project_id=other_project.id)
        )
    with pytest.raises(EntityNotFoundError):
        service.get_scans_over_time(
            user_id=owner.id,
            project_id=other_project.id,
            now=now,
        )


def test_admin_scan_reads_cover_all_users_and_support_project_filter(db_session):
    role = Role(name=UserRole.CLIENT)
    first_user = User(email="first-admin@example.com", username="first", role=role)
    second_user = User(email="second-admin@example.com", username="second", role=role)
    first_project = Project(
        name="First",
        repo_owner="first",
        repo_name="one",
        branch="main",
        user=first_user,
    )
    second_project = Project(
        name="Second",
        repo_owner="second",
        repo_name="two",
        branch="main",
        user=second_user,
    )
    now = datetime(2026, 7, 13, 12, tzinfo=timezone.utc)
    db_session.add_all([
        Scan(project=first_project, created_at=now - timedelta(days=2)),
        Scan(project=second_project, created_at=now - timedelta(days=1)),
    ])
    db_session.commit()

    service = ScanService(ScanRepository(db_session), MagicMock())
    all_scans = service.list_admin_scans(AdminScanListFilters())
    filtered_scans = service.list_admin_scans(
        AdminScanListFilters(project_id=first_project.id)
    )
    filtered_timeline = service.get_scans_over_time(
        project_id=first_project.id,
        now=now,
    )

    assert all_scans.total_count == 2
    assert {scan.owner.username for scan in all_scans.items} == {"first", "second"}
    assert filtered_scans.total_count == 1
    assert filtered_scans.items[0].project.name == "First"
    assert filtered_timeline.points[-3].count == 1
    assert sum(point.count for point in filtered_timeline.points) == 1


def test_scan_routes_enforce_role_exclusive_permissions(client: TestClient):
    scan_service = MagicMock()
    scan_service.get_scans_over_time.return_value = ScanTimelineResponse(points=[])
    scan_service.list_admin_scans.return_value = AdminScanListResult(
        items=[],
        total_count=0,
    )
    client.app.dependency_overrides[get_scan_service] = lambda: scan_service

    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub=str(uuid.uuid4()),
        role="admin",
    )
    assert client.get("/api/v1/scans").status_code == 403
    assert client.get("/api/v1/scans-over-time").status_code == 403
    assert client.post(f"/api/v1/projects/{uuid.uuid4()}/scans").status_code == 403

    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub=str(uuid.uuid4()),
        role="client",
    )
    assert client.get("/api/v1/admin/scans").status_code == 403
    assert client.get("/api/v1/admin/analytics/scans-over-time").status_code == 403

    project_id = uuid.uuid4()
    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub=str(uuid.uuid4()),
        role="admin",
    )
    admin_list = client.get(
        "/api/v1/admin/scans",
        params={"project_id": str(project_id), "page": 2, "limit": 5},
    )
    admin_timeline = client.get(
        "/api/v1/admin/analytics/scans-over-time",
        params={"project_id": str(project_id)},
    )

    assert admin_list.status_code == 200
    assert admin_list.json()["meta"]["pagination"]["page"] == 2
    assert admin_timeline.status_code == 200
    filters = scan_service.list_admin_scans.call_args.args[0]
    assert filters.project_id == project_id
    assert filters.page == 2
    assert filters.limit == 5
    scan_service.get_scans_over_time.assert_called_with(project_id=project_id)
