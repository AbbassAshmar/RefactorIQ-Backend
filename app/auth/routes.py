from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse

from app.core.route_dependencies import get_current_payload
from app.auth.services.auth_service import AuthService
from app.auth.services.oauth_service import OAuthService
from app.auth.utils import COOKIE_NAME
from app.core.security import encrypt_token
from app.dependencies import get_auth_service, get_oauth_service, get_user_service
from app.schemas.auth import AdminLoginRequest, AuthResponse, TokenPayload
from app.schemas.user import UserResponse
from app.users.services.service import UserService
from app.utils.response import ApiResponse


FRONTEND_URL = "http://localhost:3000"
router = APIRouter(prefix="/auth", tags=["Authentication"])

COOKIE_MAX_AGE = 30 * 24 * 60 * 60


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
        path="/",
    )


# ── Admin login ──────────────────────────────────────────────

@router.post("/admin/login")
def admin_login(
    body: AdminLoginRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
):
    token, user = auth_service.authenticate_admin(body.email, body.password)
    _set_auth_cookie(response, token)

    return ApiResponse.success(
        data=AuthResponse(
            message="Login successful",
            user_id=str(user.id),
            role=user.role.name,
        ).model_dump()
    )


# ── GitHub OAuth ─────────────────────────────────────────────

@router.get("/github/authorize")
def github_authorize(
    oauth_service: OAuthService = Depends(get_oauth_service),
):
    state = secrets.token_urlsafe(32)
    url = oauth_service.get_github_authorize_url(state=state)
    return ApiResponse.success(data={"authorize_url": url, "state": state})


@router.get("/github/callback")
async def github_callback(
    code: str,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    oauth_service: OAuthService = Depends(get_oauth_service),
    state: str | None = None,
):
    github_token = await oauth_service.exchange_code_for_token(code)
    github_user_data = await oauth_service.get_github_user(github_token)
    encrypted = encrypt_token(github_token)

    jwt_token, user = auth_service.authenticate_github_user(
        github_user_data, encrypted
    )

    redirect_response = RedirectResponse(
        url=f"{FRONTEND_URL}/dashboard",
        status_code=302,
    )

    _set_auth_cookie(redirect_response, jwt_token)
    return redirect_response


# ── Logout / Me ──────────────────────────────────────────────

@router.post("/logout")
def logout(
    response: Response,
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
):
    user_service.get_user(uuid.UUID(payload.sub))
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return ApiResponse.success(data={"message": "Logged out successfully"})


@router.get("/me")
def get_me(
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
):
    current_user = user_service.get_user(uuid.UUID(payload.sub))
    return ApiResponse.success(
        data={ "user": UserResponse.model_validate(current_user).model_dump() }
    )