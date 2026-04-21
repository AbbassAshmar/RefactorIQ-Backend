from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.projects.dependencies import get_project_service
from app.projects.services.service import ProjectService
from app.schemas.auth import TokenPayload
from app.schemas.project import ProjectCreate
from app.users.services.service import UserService
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
