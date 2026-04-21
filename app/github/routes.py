from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.core.route_dependencies import get_current_payload
from app.github.dependencies import get_github_service
from app.github.services.service import GithubService
from app.schemas.auth import TokenPayload
from app.utils.response import ApiResponse


router = APIRouter(prefix="/github", tags=["GitHub"])


@router.get("/repositories")
async def get_user_repositories(
    per_page: int = Query(50, ge=1, le=100),
    page: int = Query(1, ge=1),
    payload: TokenPayload = Depends(get_current_payload),
    github_service: GithubService = Depends(get_github_service),
):
    repositories = await github_service.get_user_repositories(
        uuid.UUID(payload.sub),
        per_page=per_page,
        page=page,
    )
    return ApiResponse.success(data={ "repositories": [repo.model_dump() for repo in repositories] })


@router.get("/repositories/{repo_owner}/{repo_name}/branches")
async def get_repository_branches(
    repo_owner: str,
    repo_name: str,
    per_page: int = Query(50, ge=1, le=100),
    page: int = Query(1, ge=1),
    payload: TokenPayload = Depends(get_current_payload),
    github_service: GithubService = Depends(get_github_service),
):
    branches = await github_service.get_repository_branches(
        uuid.UUID(payload.sub),
        repo_owner,
        repo_name,
        per_page=per_page,
        page=page,
    )
    return ApiResponse.success(data={ "branches": [branch.model_dump() for branch in branches] })
