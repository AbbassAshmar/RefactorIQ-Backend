from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings
from app.schemas.auth import TokenPayload


class JWTService:
    """JWT token creation and verification service."""

    def create_access_token(self, user_id: uuid.UUID, role: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "role": role,
            "iat": now,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def decode_access_token(self, token: str) -> TokenPayload | None:
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            sub: str | None = payload.get("sub")
            role: str | None = payload.get("role")
            if sub is None or role is None:
                return None
            return TokenPayload(sub=sub, role=role)
        except JWTError:
            return None
