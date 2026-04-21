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
from app.users.repositories.role_repository import RoleRepository
from app.users.repositories.repository import UserRepository
from app.users.services.service import UserService


def get_user_repository(
    db: Session = Depends(get_db),
) -> UserRepository:
    return UserRepository(db)


def build_user_repository(db: Session) -> UserRepository:
    return UserRepository(db)


def get_role_repository(
    db: Session = Depends(get_db),
) -> RoleRepository:
    return RoleRepository(db)


def build_role_repository(db: Session) -> RoleRepository:
    return RoleRepository(db)


def get_user_service(
    repo: UserRepository = Depends(get_user_repository),
    role_repo: RoleRepository = Depends(get_role_repository),
) -> UserService:
    return UserService(repo, role_repo)


def build_user_service(repo: UserRepository, role_repo: RoleRepository) -> UserService:
    return UserService(repo, role_repo)


def get_jwt_service() -> JWTService:
    return JWTService()


def get_oauth_service() -> OAuthService:
    return OAuthService()


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    role_repo: RoleRepository = Depends(get_role_repository),
    jwt_service: JWTService = Depends(get_jwt_service),
) -> AuthService:
    return AuthService(user_repo, role_repo, jwt_service)


def build_auth_service(
    user_repo: UserRepository,
    role_repo: RoleRepository,
    jwt_service: JWTService,
) -> AuthService:
    return AuthService(user_repo, role_repo, jwt_service)
