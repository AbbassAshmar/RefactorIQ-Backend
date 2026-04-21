from __future__ import annotations

import uuid

from app.auth.services.jwt_service import JWTService
from app.core.enums import UserRole
from app.core.exceptions.domain_exceptions import (
    AuthenticationError,
    AuthorizationError,
    EntityNotFoundError,
)
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.core.security import verify_password
from app.schemas.auth import TokenPayload
from app.schemas.user import UserCreate, UserInternal, UserResponse
from app.users.repositories.role_repository import RoleRepository
from app.users.repositories.repository import UserRepository

import logging
logger = logging.getLogger(__name__)

class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        role_repository: RoleRepository,
        jwt_service: JWTService,
    ) -> None:
        self._user_repo = user_repository
        self._role_repo = role_repository
        self._jwt_service = jwt_service

    def authenticate_admin(
        self, email: str, password: str
    ) -> tuple[str, UserResponse]:
        """Validate credentials and return *(jwt_token, user)*."""
        try:
            user = self._user_repo.get_by_email(email)

            if not user or not user.password:
                raise AuthenticationError("Invalid email or password")

            role = self._require_user_role(user)
            if role != UserRole.ADMIN:
                raise AuthorizationError("Admin access required")

            if not verify_password(password, user.password):
                raise AuthenticationError("Invalid email or password")

            if not user.is_active:
                raise AuthorizationError("Account is deactivated")

            token = self._jwt_service.create_access_token(user.id, role.value)
            return token, self._to_response(user)
        except DatabaseOperationException as exc:
            raise AuthenticationError("Authentication failed") from exc

    # GitHub OAuth

    def authenticate_github_user(
        self,
        github_user_data: dict,
        encrypted_github_token: str,
    ) -> tuple[str, UserResponse]:
        """Find-or-create a client user from GitHub profile data.

        Returns *(jwt_token, user)*.
        """
        try:
            github_id: int = github_user_data["id"]
            github_login: str = github_user_data.get("login", "")
            github_name: str = github_user_data.get("name") or github_login
            github_email: str | None = github_user_data.get("email")

            client_role = self._role_repo.get_by_name(UserRole.CLIENT)
            if not client_role:
                raise AuthenticationError("Default client role is not configured")

            user = self._user_repo.get_by_github_id(github_id)
            
            if user:
                logger.info(f"Updating existing GitHub user: {github_login}")
                fields = {
                    "github_access_token": encrypted_github_token,
                    "github_username": github_login,
                    "username": github_name,
                }
                if not user.role_id:
                    fields["role_id"] = client_role.id

                self._user_repo.update(
                    user.id,
                    fields,
                )
                user = self._user_repo.get_by_id(user.id)
            else:
                email = github_email or f"{github_login}@users.noreply.github.com"
                existing_by_email = self._user_repo.get_by_email(email)

                if existing_by_email:
                    fields = {
                        "github_id": github_id,
                        "github_username": github_login,
                        "github_access_token": encrypted_github_token,
                    }
                    if not existing_by_email.role_id:
                        fields["role_id"] = client_role.id

                    self._user_repo.update(
                        existing_by_email.id,
                        fields,
                    )
                    user = self._user_repo.get_by_id(existing_by_email.id)
                else:
                    logger.info(f"Creating new user from GitHub login: {github_login}")

                    user_data = UserCreate(
                        email=email,
                        username=github_name,
                        github_username=github_login,
                        github_id=github_id,
                    )
                    user = self._user_repo.create(
                        user_data,
                        role_id=client_role.id,
                        github_access_token=encrypted_github_token,
                    )

            if not user or not user.is_active:
                raise AuthorizationError("Account is deactivated")

            role = self._require_user_role(user)
            token = self._jwt_service.create_access_token(user.id, role.value)
            return token, self._to_response(user)
        except DuplicateRecordException as exc:
            logger.error(
                "GitHub account conflict for GitHub ID %s",
                github_user_data.get("id"),
            )
            raise AuthenticationError("GitHub account conflict") from exc
        except (RecordNotFoundException, DatabaseOperationException) as exc:
            logger.error(
                "GitHub authentication failed for GitHub ID %s: %s",
                github_user_data.get("id"),
                exc,
            )
            raise AuthenticationError("GitHub authentication failed") from exc

    # Helpers

    def get_user_by_id(self, user_id: uuid.UUID) -> UserResponse:
        """Return public user data for a given id (used by /auth/me)."""
        try:
            user = self._user_repo.get_by_id(user_id)
            if not user:
                raise EntityNotFoundError("user", user_id)
            return self._to_response(user)
        except DatabaseOperationException as exc:
            raise AuthenticationError("Unable to retrieve current user") from exc

    def validate_access_token(self, token: str) -> TokenPayload:
        payload = self._jwt_service.decode_access_token(token)
        if not payload:
            raise AuthenticationError("Invalid or expired token")
        return payload

    @staticmethod
    def _to_response(user: UserInternal) -> UserResponse:
        return UserResponse.model_validate(user.model_dump())

    @staticmethod
    def _require_user_role(user: UserInternal) -> UserRole:
        if user.role is None:
            raise AuthorizationError("Account role is not configured")
        return user.role
