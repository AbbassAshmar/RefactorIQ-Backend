from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, Request, Response
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
from app.core.exceptions.http_exceptions import HttpUnauthorized
import logging
logger = logging.getLogger(__name__)


FRONTEND_URL = "http://localhost:3001"
router = APIRouter(prefix="/auth", tags=["Authentication"])

COOKIE_MAX_AGE = 30 * 24 * 60 * 60


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
        path="/",
    )

def _set_github_state_cookie(response: Response, state: str) -> None:
    response.set_cookie(
        key="github_oauth_state",
        value=state,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=300,  # State is valid for 5 minutes
        path="/",
    )

def _validate_github_states(received_state: str | None, stored_state: str | None) -> None:
    if not received_state or not stored_state or received_state != stored_state:
        logger.warning(f"GitHub OAuth state mismatch: received={received_state} stored={stored_state}")
        raise HttpUnauthorized(message="Invalid or missing OAuth state parameter") 

# admin
@router.post("/admin/login")
def admin_login(
    body: AdminLoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    token, user = auth_service.authenticate_admin(body.email, body.password)
    api_response = ApiResponse.success(
        data=AuthResponse(
            message="Login successful",
            user_id=str(user.id),
            role=user.role.value if user.role else "",
        ).model_dump()
    )
    _set_auth_cookie(api_response, token)
    return api_response


# GitHub OAuth 
@router.get("/github/authorize")
def github_authorize(
    oauth_service: OAuthService = Depends(get_oauth_service),
):
    state = secrets.token_urlsafe(32)
    url = oauth_service.get_github_authorize_url(state=state)
    api_response = ApiResponse.success(data={"authorize_url": url})
    _set_github_state_cookie(api_response, state)
    return api_response


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str,
    auth_service: AuthService = Depends(get_auth_service),
    oauth_service: OAuthService = Depends(get_oauth_service),
    state: str | None = None,
):
    stored_state = request.cookies.get("github_oauth_state")
    _validate_github_states(state, stored_state)

    github_token = await oauth_service.exchange_code_for_token(code)
    github_user_data = await oauth_service.get_github_user(github_token)

    # to be removed after testing
    logger.info(f"Github token: {github_token}")
    
    encrypted = encrypt_token(github_token)

    jwt_token, user = auth_service.authenticate_github_user(
        github_user_data, encrypted
    )

    # to be removed after testing
    logger.info(f"Jwt token: {jwt_token}")

    redirect_response = RedirectResponse(
        url=f"{FRONTEND_URL}/dashboard",
        status_code=302,
    )

    redirect_response.delete_cookie("github_oauth_state")

    _set_auth_cookie(redirect_response, jwt_token)
    return redirect_response


# Logout / Me
@router.post("/logout")
def logout(
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
):
    user_service.get_user(uuid.UUID(payload.sub))
    api_response = ApiResponse.success(data={"message": "Logged out successfully"})
    api_response.delete_cookie(key=COOKIE_NAME, path="/")
    return api_response


@router.get("/me")
def get_me(
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
):
    current_user = user_service.get_user(uuid.UUID(payload.sub))
    return ApiResponse.success(
        data={ "user": UserResponse.model_validate(current_user).model_dump() }
    )