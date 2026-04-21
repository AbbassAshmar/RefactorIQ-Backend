from __future__ import annotations

from fastapi import Depends

from app.dependencies import get_user_service
from app.github.services.client_service import GithubClientService
from app.github.services.service import GithubService
from app.users.services.service import UserService


def get_github_client_service() -> GithubClientService:
    return GithubClientService()


def get_github_service(
    github_client: GithubClientService = Depends(get_github_client_service),
    user_service: UserService = Depends(get_user_service),
) -> GithubService:
    return GithubService(github_client, user_service)
