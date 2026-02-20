from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.exceptions.domain_exceptions import ExternalServiceError

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


class OAuthService:
    """GitHub OAuth helpers for authorization URL, token exchange, and profile fetch."""

    def get_github_authorize_url(self, state: str | None = None) -> str:
        params: dict[str, str] = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
            "scope": "repo",
        }
        if state:
            params["state"] = state
        return f"{GITHUB_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GITHUB_TOKEN_URL,
                json={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.GITHUB_REDIRECT_URI,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        if "access_token" not in data:
            error = data.get("error_description", "Unknown error from GitHub")
            raise ExternalServiceError(
                service="github",
                message=f"GitHub OAuth error: {error}",
            )

        return data["access_token"]

    async def get_github_user(self, access_token: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                GITHUB_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            response.raise_for_status()
            return response.json()
