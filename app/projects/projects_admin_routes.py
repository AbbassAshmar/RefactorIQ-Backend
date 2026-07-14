"""Administrative project-management routes."""

import math

from fastapi import APIRouter, Depends, Query

from app.auth.auth_dtos import TokenPayload
from app.core.common_dtos import PaginationMeta, ResponseMeta
from app.core.route_dependencies import require_permissions
from app.projects.dependencies import get_project_service
from app.projects.projects_dtos import (
    AdminProjectListFilters,
    ProjectSortBy,
    ProjectSortOrder,
)
from app.projects.projects_service import ProjectService
from app.utils.response import ApiResponse


router = APIRouter(prefix="/admin/projects", tags=["Admin Projects"])


@router.get("")
def list_admin_projects(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=100),
    sort_by: ProjectSortBy = "created_at",
    sort_order: ProjectSortOrder = "desc",
    project_service: ProjectService = Depends(get_project_service),
    _: TokenPayload = Depends(require_permissions(["manage-projects"])),
):
    result = project_service.list_admin_projects(
        AdminProjectListFilters(
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            query=q,
        )
    )
    total_pages = math.ceil(result.total_count / limit) if result.total_count else 0
    return ApiResponse.success(
        data={"projects": [project.model_dump() for project in result.items]},
        meta=ResponseMeta(
            pagination=PaginationMeta(
                page=page,
                limit=limit,
                total_pages=total_pages,
                total_count=result.total_count,
                has_next_page=page < total_pages,
                has_previous_page=page > 1,
            )
        ),
    )


@router.get("/over-time")
def get_projects_over_time(
    project_service: ProjectService = Depends(get_project_service),
    _: TokenPayload = Depends(require_permissions(["manage-projects"])),
):
    return ApiResponse.success(
        data=project_service.get_projects_over_time().model_dump()
    )
