"""Custom middleware for the FastAPI application."""

import logging
import time

from fastapi import Request
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.routing import Match

from app.auth.services.jwt_service import JWTService
from app.auth.utils import COOKIE_NAME
from app.core.database import SessionLocal
from app.dependencies import build_auth_service, build_user_repository

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status code and processing time for every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        logger.info(
            "%s %s — %s (%.3fs)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"
        return response


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Extract and validate JWT from cookie then attach payload to request state."""

    @staticmethod
    def _is_auth_required(request: Request) -> bool:
        for route in request.app.router.routes:
            match, child_scope = route.matches(request.scope)
            if match is Match.FULL:
                endpoint = child_scope.get("endpoint")
                return bool(getattr(endpoint, "requires_auth_context", False))
        return False

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.auth_payload = None

        if not self._is_auth_required(request):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)

        if token:
            db: Session = SessionLocal()
            try:
                user_repo = build_user_repository(db)
                auth_service = build_auth_service(user_repo, JWTService())
                request.state.auth_payload = auth_service.validate_access_token(token)
            finally:
                db.close()

        return await call_next(request)



