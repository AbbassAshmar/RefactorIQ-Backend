from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.projects.dependencies import get_project_service

from app.projects.projects_service import ProjectService
from app.users.users_service import UserService
from app.core.enums import UserRole
from app.core.exceptions.domain_exceptions import AuthorizationError

from app.auth.auth_dtos import TokenPayload
from app.projects.projects_dtos import ProjectCreate

from app.utils.response import ApiResponse

import logging 
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("/")
def create_project(
    body: ProjectCreate,
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    project_service: ProjectService = Depends(get_project_service),
):
    user_id = uuid.UUID(payload.sub)
    user_service.get_user(user_id)
    project = project_service.create_project(user_id, body)
    return ApiResponse.success(data={ "project": project.model_dump() })


@router.get("/")
def list_user_projects(
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    project_service: ProjectService = Depends(get_project_service),
):
    logger.info(f"Listing projects : {payload.sub}")
    user_id = uuid.UUID(payload.sub)
    user_service.get_user(user_id)
    projects = project_service.list_user_projects(user_id)
    return ApiResponse.success(data={ "projects": [project.model_dump() for project in projects] })


@router.delete("/{project_id}")
def delete_project(
    project_id: uuid.UUID,
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    project_service: ProjectService = Depends(get_project_service),
):
    user_id = uuid.UUID(payload.sub)
    logger.info(
        "[PROJECT DELETE REQUESTED] project_id=%s user_id=%s role=%s",
        project_id,
        user_id,
        payload.role,
    )
    if payload.role != UserRole.CLIENT.value:
        logger.warning(
            "[PROJECT DELETE FORBIDDEN] project_id=%s user_id=%s role=%s",
            project_id,
            user_id,
            payload.role,
        )
        raise AuthorizationError("Only clients can delete projects")

    user_service.get_user(user_id)
    logger.info(
        "[PROJECT DELETE AUTHORIZED] project_id=%s user_id=%s role=%s",
        project_id,
        user_id,
        payload.role,
    )
    project_service.delete_project(project_id, user_id)
    logger.info("[PROJECT DELETE RESPONSE] project_id=%s user_id=%s", project_id, user_id)
    return ApiResponse.success(
        data={
            "message": "Project deleted successfully",
            "project_id": str(project_id),
        }
    )
