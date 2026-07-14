from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.auth.auth_dtos import TokenPayload
from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.files.dependencies import get_file_service
from app.files.files_dtos import (
    CircularDependency,
    DependencyEdgeReference,
    DependencyGraphResponse,
    FileReference,
    ScanCircularDependenciesResponse,
)


def _authenticated_services(client: TestClient):
    user_id = uuid.uuid4()
    user_service = MagicMock()
    file_service = MagicMock()
    client.app.dependency_overrides[get_current_payload] = lambda: TokenPayload(sub=str(user_id), role='client')
    client.app.dependency_overrides[get_user_service] = lambda: user_service
    client.app.dependency_overrides[get_file_service] = lambda: file_service
    return user_id, user_service, file_service


def test_dependency_routes_require_authentication(client: TestClient):
    scan_id = uuid.uuid4()

    assert client.get('/api/v1/files/dependencies', params={'scan_id': str(scan_id)}).status_code == 401
    assert client.get('/api/v1/files/circular-dependencies', params={'scan_id': str(scan_id)}).status_code == 401


def test_dependency_routes_require_scan_id(client: TestClient):
    _authenticated_services(client)

    assert client.get('/api/v1/files/dependencies').status_code == 422
    assert client.get('/api/v1/files/circular-dependencies').status_code == 422


def test_non_uuid_file_path_does_not_capture_static_file_routes(client: TestClient):
    _authenticated_services(client)

    response = client.get('/api/v1/files/not-a-file-id')

    assert response.status_code == 404


def test_dependency_routes_return_scan_snapshots(client: TestClient):
    user_id, user_service, file_service = _authenticated_services(client)
    scan_id = uuid.uuid4()
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    group_id = uuid.uuid4()
    source = FileReference(id=source_id, file_path='src/a.py', priority_band='high')
    target = FileReference(id=target_id, file_path='src/b.py', priority_band='medium')
    file_service.list_scan_dependencies.return_value = DependencyGraphResponse(
        scan_id=scan_id,
        nodes=[source, target],
        edges=[DependencyEdgeReference(source_file_id=source_id, target_file_id=target_id)],
    )
    file_service.list_scan_circular_dependencies.return_value = ScanCircularDependenciesResponse(
        scan_id=scan_id,
        circular_dependencies=[CircularDependency(group_id=group_id, size=2, members=[source, target])],
    )

    graph_response = client.get('/api/v1/files/dependencies', params={'scan_id': str(scan_id)})
    cycles_response = client.get('/api/v1/files/circular-dependencies', params={'scan_id': str(scan_id)})

    assert graph_response.status_code == 200
    assert graph_response.json()['data']['edges'][0] == {
        'source_file_id': str(source_id),
        'target_file_id': str(target_id),
    }
    assert graph_response.json()['meta']['scan_id'] == str(scan_id)
    assert cycles_response.status_code == 200
    assert cycles_response.json()['data']['circular_dependencies'][0]['group_id'] == str(group_id)
    file_service.list_scan_dependencies.assert_called_once_with(user_id, scan_id)
    file_service.list_scan_circular_dependencies.assert_called_once_with(user_id, scan_id)
    assert user_service.get_user.call_count == 2
