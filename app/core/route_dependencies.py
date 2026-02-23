from __future__ import annotations

from typing import Iterable

from fastapi import Depends, Request


from app.auth.services.auth_service import AuthService
from app.core.enums import UserRole
from app.dependencies import get_auth_service, get_db
from app.schemas.auth import TokenPayload
from app.auth.utils import COOKIE_NAME


from app.core.exceptions.domain_exceptions import (
    AuthenticationError,
    AuthorizationError,
)


COOKIE_NAME = "access_token"

_ROLE_PERMISSIONS: dict[str, list[str]] = {
    UserRole.ADMIN.value: ["manage-users", "manage-scans"],
    UserRole.CLIENT.value: [],
}


# ──────────────────────────────────────────────────────────────
# Authentication Dependency
# ──────────────────────────────────────────────────────────────

async def get_current_payload(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPayload:
    """
    Extract JWT from cookie and validate it.
    Raises 401 if missing/invalid.
    """

    token = request.cookies.get(COOKIE_NAME)

    if not token:
        raise AuthenticationError("Not authenticated")

    try:
        payload = auth_service.validate_access_token(token)
    except Exception:
        raise AuthenticationError("Invalid authentication payload")

    return payload


# ──────────────────────────────────────────────────────────────
# Authorization Dependencies
# ──────────────────────────────────────────────────────────────


def require_permissions(required_permissions: Iterable[str]):
    """
    Checks that ALL required permissions exist.
    Automatically requires authentication first.
    """

    async def dependency(
        payload: TokenPayload = Depends(get_current_payload),
    ) -> TokenPayload:


        user_perms = _ROLE_PERMISSIONS.get(payload.role, [])

        for perm in required_permissions:
            if perm not in user_perms:
                raise AuthorizationError(
                    f"Permission '{perm}' required"
                )

        return payload

    return dependency