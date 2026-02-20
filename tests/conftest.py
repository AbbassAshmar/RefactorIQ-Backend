"""Shared pytest fixtures for the test suite."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.jwt import create_access_token
from app.core.database import get_db
from app.core.enums import UserRole
from app.main import app
from app.models.base import Base

# ── In-memory SQLite for fast tests ──────────────────────────

SQLALCHEMY_TEST_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Create tables, yield a session, then tear down."""
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI ``TestClient`` wired to the test database session."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helper factories ─────────────────────────────────────────

_NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_admin_user_dict(**overrides) -> dict:
    """Return a dict that looks like a ``UserInternal`` dump for an admin."""
    defaults = {
        "id": uuid.uuid4(),
        "email": "admin@example.com",
        "full_name": "Admin User",
        "hashed_password": "hashed",
        "role": UserRole.ADMIN,
        "github_access_token": None,
        "github_username": None,
        "github_id": None,
        "is_active": True,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return defaults


def make_client_user_dict(**overrides) -> dict:
    """Return a dict that looks like a ``UserInternal`` dump for a client."""
    defaults = {
        "id": uuid.uuid4(),
        "email": "client@example.com",
        "full_name": "Client User",
        "hashed_password": None,
        "role": UserRole.CLIENT,
        "github_access_token": "encrypted-token",
        "github_username": "octocat",
        "github_id": 12345,
        "is_active": True,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture()
def admin_token() -> str:
    """A valid JWT for an admin user (useful for authenticated requests)."""
    return create_access_token(uuid.uuid4(), UserRole.ADMIN.value)


@pytest.fixture()
def client_token() -> str:
    """A valid JWT for a client user."""
    return create_access_token(uuid.uuid4(), UserRole.CLIENT.value)
