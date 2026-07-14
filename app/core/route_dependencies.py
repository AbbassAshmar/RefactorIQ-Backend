from __future__ import annotations

from typing import Iterable

from fastapi import Depends, Request


from app.auth.services.auth_service import AuthService
from app.core.constants import COOKIE_NAME, ROLE_PERMISSIONS
from app.core.enums import UserRole
from app.dependencies import get_auth_service, get_db
from app.auth.auth_dtos import TokenPayload


from app.core.exceptions.domain_exceptions import (
    AuthenticationError,
    AuthorizationError,
)


# Authentication

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



# Authorization

def require_permissions(required_permissions: Iterable[str]):
    """
    Checks that ALL required permissions exist.
    Automatically requires authentication first.
    """

    permissions = (
        [required_permissions]
        if isinstance(required_permissions, str)
        else required_permissions
    )

    async def dependency(
        payload: TokenPayload = Depends(get_current_payload),
    ) -> TokenPayload:


        user_perms = ROLE_PERMISSIONS.get(payload.role, [])

        for perm in permissions:
            if perm not in user_perms:
                raise AuthorizationError(
                    f"Permission '{perm}' required"
                )

        return payload

    return dependency
