from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.overview.dependencies import get_overview_service
from app.overview.overview_dtos import DirectoryInsightResponse, RiskTrendPoint, RiskTrendResponse
from app.auth.auth_dtos import TokenPayload


def test_overview_requires_authentication(client: TestClient):
    response = client.get('/api/v1/overview/risk-trend', params={'scan_id': str(uuid.uuid4())})
    assert response.status_code == 401


def test_risk_trend_returns_scan_id_in_metadata(client: TestClient):
    user_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    response_model = RiskTrendResponse(
        scan_id=scan_id,
        series=[
            RiskTrendPoint(
                scan_id=scan_id,
                finished_at=datetime.now(timezone.utc),
                average_score=42.5,
            )
        ],
    )

    user_service = MagicMock()
    overview_service = MagicMock()
    overview_service.risk_trend.return_value = response_model

    app = client.app
    app.dependency_overrides[get_current_payload] = lambda: TokenPayload(sub=str(user_id), role='client')
    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_overview_service] = lambda: overview_service

    response = client.get('/api/v1/overview/risk-trend', params={'scan_id': str(scan_id)})

    assert response.status_code == 200
    body = response.json()
    assert body['data']['series'][0]['average_score'] == 42.5
    assert body['meta']['scan_id'] == str(scan_id)
    overview_service.risk_trend.assert_called_once_with(user_id, scan_id)


def test_directory_insight_returns_structured_recommendation(client: TestClient):
    user_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    response_model = DirectoryInsightResponse(
        scan_id=scan_id,
        title='Recommended focus area',
        summary='Risk is mostly concentrated in auth.',
        explanation='This area contains important files used by multiple features.',
        recommendation='Review auth this sprint before broader refactoring.',
        priority_directories=[
            {'path': 'src/services/auth', 'priority': 'high', 'reason': 'Highest concentration of risky files'},
        ],
    )

    user_service = MagicMock()
    overview_service = MagicMock()
    overview_service.directory_insight.return_value = response_model

    app = client.app
    app.dependency_overrides[get_current_payload] = lambda: TokenPayload(sub=str(user_id), role='client')
    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_overview_service] = lambda: overview_service

    response = client.get('/api/v1/overview/directory-insight', params={'scan_id': str(scan_id)})

    assert response.status_code == 200
    body = response.json()
    assert body['data']['title'] == 'Recommended focus area'
    assert body['data']['priority_directories'][0]['priority'] == 'high'
    overview_service.directory_insight.assert_called_once_with(user_id, scan_id)
