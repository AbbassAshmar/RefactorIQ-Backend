"""Global dependency-injection wiring.

Exposes factory functions consumed by ``Depends(...)`` in route handlers.
Each function composes repositories and services so the layers remain
decoupled.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth.services.auth_service import AuthService
from app.auth.services.jwt_service import JWTService
from app.auth.services.oauth_service import OAuthService
from app.core.database import get_db
from app.users.repositories.repository import UserRepository
from app.users.services.service import UserService


def get_user_repository(
    db: Session = Depends(get_db),
) -> UserRepository:
    return UserRepository(db)


def build_user_repository(db: Session) -> UserRepository:
    return UserRepository(db)


def get_user_service(
    repo: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(repo)


def build_user_service(repo: UserRepository) -> UserService:
    return UserService(repo)


def get_jwt_service() -> JWTService:
    return JWTService()


def get_oauth_service() -> OAuthService:
    return OAuthService()


def get_auth_service(
    repo: UserRepository = Depends(get_user_repository),
    jwt_service: JWTService = Depends(get_jwt_service),
) -> AuthService:
    return AuthService(repo, jwt_service)


def build_auth_service(repo: UserRepository, jwt_service: JWTService) -> AuthService:
    return AuthService(repo, jwt_service)
