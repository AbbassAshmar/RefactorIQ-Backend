from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.auth.auth_dtos import TokenPayload
from app.core.enums import ScanStatus, UserRole
from app.core.route_dependencies import get_current_payload
from app.models import Project, Role, Scan, User
from app.projects.dependencies import get_project_service
from app.projects.projects_dtos import (
    AdminProjectListFilters,
    AdminProjectListResult,
    AdminProjectOwner,
    AdminProjectResponse,
)
from app.projects.projects_repository import ProjectRepository


def test_admin_projects_sort_by_count_duration_and_owner(db_session):
    role = Role(name=UserRole.CLIENT)
    alpha = User(email="alpha@example.com", username="Alpha", role=role)
    zulu = User(email="zulu@example.com", username="zulu", role=role)
    frequent = Project(
        name="Frequent",
        repo_owner="org",
        repo_name="frequent",
        branch="main",
        user=zulu,
    )
    slow = Project(
        name="Slow",
        repo_owner="org",
        repo_name="slow",
        branch="main",
        user=alpha,
    )
    empty = Project(
        name="Empty",
        repo_owner="org",
        repo_name="empty",
        branch="main",
        user=alpha,
    )
    start = datetime(2026, 7, 13, tzinfo=timezone.utc)
    frequent.scans = [
        Scan(
            status=ScanStatus.SUCCEEDED,
            started_at=start,
            finished_at=start + timedelta(seconds=60),
        ),
        Scan(
            status=ScanStatus.FAILED,
            started_at=start,
            finished_at=start + timedelta(seconds=120),
        ),
    ]
    slow.scans = [
        Scan(
            status=ScanStatus.SUCCEEDED,
            started_at=start,
            finished_at=start + timedelta(seconds=300),
        )
    ]
    db_session.add_all([frequent, slow, empty])
    db_session.commit()
    repository = ProjectRepository(db_session)

    duration_rows, total = repository.list_admin_projects(
        AdminProjectListFilters(sort_by="scan_duration", sort_order="desc")
    )
    count_rows, _ = repository.list_admin_projects(
        AdminProjectListFilters(sort_by="scan_count", sort_order="desc")
    )
    owner_rows, _ = repository.list_admin_projects(
        AdminProjectListFilters(sort_by="owner", sort_order="asc")
    )

    assert total == 3
    assert [row.name for row in duration_rows] == ["Slow", "Frequent", "Empty"]
    assert duration_rows[0].average_scan_duration_seconds == 300.0
    assert duration_rows[1].average_scan_duration_seconds == 90.0
    assert duration_rows[2].average_scan_duration_seconds is None
    assert count_rows[0].name == "Frequent"
    assert count_rows[0].scan_count == 2
    assert [row.owner_username for row in owner_rows[:2]] == ["Alpha", "Alpha"]


def test_user_project_list_derives_status_from_scans(db_session):
    role = Role(name=UserRole.CLIENT)
    user = User(email="client@example.com", username="client", role=role)
    running_project = Project(
        name="Running",
        repo_owner="org",
        repo_name="running",
        branch="main",
        user=user,
    )
    latest_status_project = Project(
        name="Latest Status",
        repo_owner="org",
        repo_name="latest-status",
        branch="main",
        user=user,
    )
    empty_project = Project(
        name="Empty",
        repo_owner="org",
        repo_name="empty",
        branch="main",
        user=user,
    )
    start = datetime(2026, 7, 13, tzinfo=timezone.utc)
    running_project.scans = [
        Scan(
            status=ScanStatus.RUNNING,
            created_at=start,
            updated_at=start,
        ),
        Scan(
            status=ScanStatus.FAILED,
            created_at=start + timedelta(minutes=1),
            updated_at=start + timedelta(minutes=1),
        ),
    ]
    latest_status_project.scans = [
        Scan(
            status=ScanStatus.SUCCEEDED,
            created_at=start,
            updated_at=start,
        ),
        Scan(
            status=ScanStatus.FAILED,
            created_at=start + timedelta(minutes=1),
            updated_at=start + timedelta(minutes=1),
        ),
    ]
    db_session.add_all([running_project, latest_status_project, empty_project])
    db_session.commit()

    projects = ProjectRepository(db_session).list_by_user_id(user.id)
    statuses = {project.name: project.status for project in projects}

    assert statuses == {
        "Running": ScanStatus.RUNNING,
        "Latest Status": ScanStatus.FAILED,
        "Empty": None,
    }


def test_admin_projects_route_paginates_and_passes_sort_filters(client: TestClient):
    now = datetime.now(timezone.utc)
    item = AdminProjectResponse(
        id=__import__("uuid").uuid4(),
        user_id=__import__("uuid").uuid4(),
        name="Top Project",
        repo_owner="org",
        repo_name="top",
        branch="main",
        created_at=now,
        updated_at=now,
        owner=AdminProjectOwner(
            id=__import__("uuid").uuid4(),
            username="owner",
            email="owner@example.com",
        ),
        scan_count=12,
        average_scan_duration_seconds=42.5,
    )
    service = MagicMock()
    service.list_admin_projects.return_value = AdminProjectListResult(
        items=[item],
        total_count=11,
    )
    client.app.dependency_overrides[get_project_service] = lambda: service

    assert client.get("/api/v1/admin/projects").status_code == 401
    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(
        sub="00000000-0000-0000-0000-000000000001",
        role="admin",
    )
    response = client.get(
        "/api/v1/admin/projects",
        params={
            "page": 2,
            "limit": 5,
            "sort_by": "scan_count",
            "sort_order": "desc",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["projects"][0]["owner"]["username"] == "owner"
    assert body["meta"]["pagination"]["total_pages"] == 3
    filters = service.list_admin_projects.call_args.args[0]
    assert filters == AdminProjectListFilters(
        page=2,
        limit=5,
        sort_by="scan_count",
        sort_order="desc",
    )

    invalid = client.get(
        "/api/v1/admin/projects",
        params={"sort_by": "unknown"},
    )
    assert invalid.status_code == 422
