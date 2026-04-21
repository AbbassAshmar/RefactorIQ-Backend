from __future__ import annotations

import uuid

from app.core.exceptions.domain_exceptions import ConflictError, EntityNotFoundError
from app.core.security import decrypt_token
from app.github.services.client_service import GithubClientService
from app.schemas.github import GithubBranchResponse, GithubRepositoryResponse
from app.users.services.service import UserService


class GithubService:
    def __init__(
        self,
        github_client_service: GithubClientService,
        user_service: UserService,
    ) -> None:
        self._github_client = github_client_service
        self._user_service = user_service

    async def get_user_repositories(
        self,
        user_id: uuid.UUID,
        *,
        per_page: int = 50,
        page: int = 1,
    ) -> list[GithubRepositoryResponse]:
        user = self._get_user_or_fail(user_id)
        access_token = self._get_decrypted_access_token(user.github_access_token)
        repositories = await self._github_client.get_user_repositories(
            user.github_username,
            access_token,
            per_page=per_page,
            page=page,
        )
        return self._format_repositories(repositories)

    async def get_repository_branches(
        self,
        user_id: uuid.UUID,
        repo_owner: str,
        repo_name: str,
        *,
        per_page: int = 50,
        page: int = 1,
    ) -> list[GithubBranchResponse]:
        user = self._get_user_or_fail(user_id)
        access_token = self._get_decrypted_access_token(user.github_access_token)
        branches = await self._github_client.get_repository_branches(
            repo_owner,
            repo_name,
            access_token,
            per_page=per_page,
            page=page,
        )
        return self._format_branches(branches)

    def _get_user_or_fail(self, user_id: uuid.UUID):
        user = self._user_service.get_user_internal(user_id)
        if not user:
            raise EntityNotFoundError("user", user_id)
        if not user.github_username:
            raise ConflictError("GitHub username is missing for this user")
        return user

    @staticmethod
    def _get_decrypted_access_token(encrypted_token: str | None) -> str:
        if not encrypted_token:
            raise ConflictError("GitHub access token is missing for this user")
        try:
            return decrypt_token(encrypted_token)
        except ValueError as exc:
            raise ConflictError("GitHub access token is invalid") from exc

    def _format_repositories(
        self,
        repositories: list[dict],
    ) -> list[GithubRepositoryResponse]:
        return [
            GithubRepositoryResponse(
                name=repo["name"],
                owner=repo["owner"]["login"],
                full_name=repo["full_name"],
                private=repo["private"],
                default_branch=repo["default_branch"],
                html_url=repo["html_url"],
            )
            for repo in repositories
        ]

    def _format_branches(self, branches: list[dict]) -> list[GithubBranchResponse]:
        return [
            GithubBranchResponse(
                name=branch["name"],
                commit_sha=branch["commit"]["sha"],
                protected=branch["protected"],
            )
            for branch in branches
        ]
