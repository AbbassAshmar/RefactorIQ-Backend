from __future__ import annotations

import httpx

from app.core.exceptions.http_exceptions import (
    HttpBadGateway,
    HttpBadRequest,
    HttpNotFound,
    HttpUnauthorized,
)


class GithubClientService:
    BASE_URL = "https://api.github.com"

    @staticmethod
    def _headers(access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

    @staticmethod
    def _handle_http_error(exc: httpx.HTTPStatusError) -> None:
        status_code = exc.response.status_code
        if status_code == 401:
            raise HttpUnauthorized("GitHub token is invalid or expired") from exc
        if status_code == 404:
            raise HttpNotFound("GitHub resource not found") from exc
        if status_code == 400:
            raise HttpBadRequest("Bad request to GitHub API") from exc
        raise HttpBadGateway("GitHub API request failed") from exc

    async def get_user_repositories(
        self,
        username: str,
        access_token: str,
        *,
        per_page: int = 50,
        page: int = 1,
    ) -> list[dict]:
        url = f"{self.BASE_URL}/users/{username}/repos"
        params = {
            "type": "owner",
            "sort": "created",
            "direction": "desc",
            "per_page": per_page,
            "page": page,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._headers(access_token),
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                self._handle_http_error(exc)
            except httpx.RequestError as exc:
                raise HttpBadGateway("Could not reach GitHub API") from exc

    async def get_repository_branches(
        self,
        owner: str,
        repo_name: str,
        access_token: str,
        *,
        per_page: int = 50,
        page: int = 1,
    ) -> list[dict]:
        url = f"{self.BASE_URL}/repos/{owner}/{repo_name}/branches"
        params = {"per_page": per_page, "page": page}
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers=self._headers(access_token),
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                self._handle_http_error(exc)
            except httpx.RequestError as exc:
                raise HttpBadGateway("Could not reach GitHub API") from exc
