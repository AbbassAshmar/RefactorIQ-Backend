from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.scans.dependencies import get_scan_service
from app.auth.auth_dtos import TokenPayload
from app.scans.scans_dtos import ScanListResult, ScanResponse


def test_list_scans_requires_authentication(client: TestClient):
    response = client.get('/api/v1/scans')
    assert response.status_code == 401


def test_list_scans_passes_filters_and_returns_pagination(client: TestClient):
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    scan = ScanResponse(
        id=uuid.uuid4(),
        project_id=project_id,
        status='succeeded',
        started_at=now,
        finished_at=now,
        created_at=now,
        updated_at=now,
    )
    user_service = MagicMock()
    scan_service = MagicMock()
    scan_service.list_scans.return_value = ScanListResult(items=[scan], total_count=11)

    app = client.app
    app.dependency_overrides[get_current_payload] = lambda: TokenPayload(sub=str(user_id), role='client')
    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_scan_service] = lambda: scan_service

    response = client.get(
        '/api/v1/scans',
        params={
            'project_id': str(project_id),
            'status': 'succeeded',
            'sort': 'date_asc',
            'page': 2,
            'limit': 5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body['data']['scans'][0]['id'] == str(scan.id)
    assert body['meta']['pagination'] == {
        'page': 2,
        'limit': 5,
        'total_pages': 3,
        'total_count': 11,
        'has_next_page': True,
        'has_previous_page': True,
    }
    filters = scan_service.list_scans.call_args.args[0]
    assert filters.user_id == user_id
    assert filters.project_id == project_id
    assert filters.status == 'succeeded'
    assert filters.sort_descending is False
    assert filters.page == 2
    assert filters.limit == 5
