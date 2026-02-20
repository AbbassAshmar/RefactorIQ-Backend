from __future__ import annotations

from fastapi import Depends, Request

from app.core.enums import UserRole
from app.core.exceptions.domain_exceptions import (
    AuthenticationError,
    AuthorizationError,
)
from app.schemas.auth import TokenPayload

COOKIE_NAME = "access_token"

_ROLE_PERMISSIONS: dict[str, list[str]] = {
    UserRole.ADMIN.value: ["manage-users", "manage-scans"],
    UserRole.CLIENT.value: [],
}


def get_current_payload(request: Request) -> TokenPayload:
    payload = getattr(request.state, "auth_payload", None)
    if payload is None:
        raise AuthenticationError("Not authenticated")
    if not isinstance(payload, TokenPayload):
        raise AuthenticationError("Invalid authentication payload")
    return payload


def require_admin(
    payload: TokenPayload = Depends(get_current_payload),
) -> TokenPayload:
    if payload.role != UserRole.ADMIN.value:
        raise AuthorizationError("Admin access required")
    return payload


def require_permission(permission_name: str):
    def _check(
        payload: TokenPayload = Depends(get_current_payload),
    ) -> TokenPayload:
        user_perms = _ROLE_PERMISSIONS.get(payload.role, [])
        if permission_name not in user_perms:
            raise AuthorizationError(
                f"Permission '{permission_name}' required"
            )
        return payload

    return _check
