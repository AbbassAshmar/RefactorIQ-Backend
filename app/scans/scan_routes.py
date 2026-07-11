
import math
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.core.enums import ScanStatus
from app.schemas.response import PaginationMeta, ResponseMeta
from app.schemas.scan import ScanListFilters
from app.schemas.auth import TokenPayload
from app.dependencies import get_user_service
from app.core.route_dependencies import get_current_payload
from app.projects.dependencies import get_project_service
from app.utils.response import ApiResponse

from app.users.services.service import UserService
from app.scans.services.scan_service import ScanService
from app.projects.services.service import ProjectService
from app.scans.dependencies import get_scan_service

import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Scans"])


@router.get("/scans")
def list_scans(
    project_id: uuid.UUID | None = None,
    status: ScanStatus | None = None,
    sort: Literal["date_desc", "date_asc"] = "date_desc",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    scan_service: ScanService = Depends(get_scan_service),
):
    user_id = uuid.UUID(payload.sub)
    user_service.get_user(user_id)
    result = scan_service.list_scans(
        ScanListFilters(
            user_id=user_id,
            project_id=project_id,
            status=status.value if status else None,
            page=page,
            limit=limit,
            sort_descending=sort == "date_desc",
        )
    )
    total_pages = math.ceil(result.total_count / limit) if result.total_count else 0
    return ApiResponse.success(
        data={"scans": [scan.model_dump() for scan in result.items]},
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

@router.post("/projects/{project_id}/scans")
def scan_project(
    project_id: uuid.UUID,
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    project_service: ProjectService = Depends(get_project_service),
    scan_service: ScanService = Depends(get_scan_service),
):
    logger.info(f"Initiating scan for project {project_id} by user {payload.sub}")
    user_id = uuid.UUID(payload.sub)
    user_service.get_user(user_id)

    project_uuid = uuid.UUID(str(project_id))
    project_service.get_project_by_id(project_uuid, user_id)

    logger.info(f"Creating and enqueuing scan for project {project_id}")
    scan = scan_service.create_and_enqueue_scan(project_uuid)
    return ApiResponse.success(data={ "scan": scan.model_dump() })
