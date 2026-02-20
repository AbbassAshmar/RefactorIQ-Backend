"""Smoke tests for authentication endpoints."""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["status"] == "healthy"


def test_admin_login_invalid_credentials(client: TestClient):
    response = client.post(
        "/api/v1/auth/admin/login",
        json={"email": "nobody@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


def test_github_authorize_returns_url(client: TestClient):
    response = client.get("/api/v1/auth/github/authorize")
    assert response.status_code == 200
    data = response.json()
    assert "authorize_url" in data["data"]
    assert "github.com" in data["data"]["authorize_url"]


def test_me_unauthenticated(client: TestClient):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_logout_unauthenticated(client: TestClient):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 401
