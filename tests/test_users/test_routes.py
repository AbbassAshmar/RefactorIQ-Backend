"""Smoke tests for user management endpoints."""

from fastapi.testclient import TestClient


def test_list_users_unauthenticated(client: TestClient):
    response = client.get("/api/v1/users/")
    assert response.status_code == 401


def test_get_user_unauthenticated(client: TestClient):
    response = client.get(
        "/api/v1/users/00000000-0000-0000-0000-000000000001"
    )
    assert response.status_code == 401
