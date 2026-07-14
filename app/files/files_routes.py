from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, Query

from app.core.route_dependencies import get_current_payload
from app.core.route_dependencies import require_permissions
from app.dependencies import get_user_service
from app.core.common_dtos import ResponseMeta
from app.core.constants import INCLUDE_SUMMARY_QUERY_PARAM, PROJECT_ID_QUERY_PARAM, SCAN_ID_QUERY_PARAM
from app.files.dependencies import get_file_service
from app.files.files_service import FileService
from app.auth.auth_dtos import TokenPayload
from app.users.users_service import UserService
from app.utils.response import ApiResponse


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["Files"])


def _current_user_id(payload: TokenPayload, user_service: UserService) -> uuid.UUID:
    user_id = uuid.UUID(payload.sub)
    logger.debug("Validating files request user user_id=%s", user_id)
    user_service.get_user(user_id)
    logger.debug("Validated files request user user_id=%s", user_id)
    return user_id


@router.get("")
def list_scan_files(
    scan_id: uuid.UUID = Query(..., alias=SCAN_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: FileService = Depends(get_file_service),
):
    response = service.list_scan_files(_current_user_id(payload, user_service), scan_id)
    return ApiResponse.success(data=response.model_dump(), meta=ResponseMeta(scan_id=scan_id))


@router.get("/dependencies")
def list_scan_dependencies(
    scan_id: uuid.UUID = Query(..., alias=SCAN_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: FileService = Depends(get_file_service),
):
    started_at = time.perf_counter()
    user_id = _current_user_id(payload, user_service)
    logger.info("Dependency graph request started user_id=%s scan_id=%s", user_id, scan_id)
    response = service.list_scan_dependencies(user_id, scan_id)
    logger.info(
        "Dependency graph request completed user_id=%s scan_id=%s nodes=%d edges=%d duration_ms=%.2f",
        user_id,
        scan_id,
        len(response.nodes),
        len(response.edges),
        (time.perf_counter() - started_at) * 1000,
    )
    return ApiResponse.success(data=response.model_dump(), meta=ResponseMeta(scan_id=scan_id))


@router.get("/circular-dependencies")
def list_scan_circular_dependencies(
    scan_id: uuid.UUID = Query(..., alias=SCAN_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: FileService = Depends(get_file_service),
):
    started_at = time.perf_counter()
    user_id = _current_user_id(payload, user_service)
    logger.info("Circular dependencies request started user_id=%s scan_id=%s", user_id, scan_id)
    response = service.list_scan_circular_dependencies(user_id, scan_id)
    logger.info(
        "Circular dependencies request completed user_id=%s scan_id=%s groups=%d duration_ms=%.2f",
        user_id,
        scan_id,
        len(response.circular_dependencies),
        (time.perf_counter() - started_at) * 1000,
    )
    return ApiResponse.success(data=response.model_dump(), meta=ResponseMeta(scan_id=scan_id))


@router.get("/analytics/priority-distribution")
def get_project_priority_distribution(
    project_id: uuid.UUID = Query(..., alias=PROJECT_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(require_permissions(["view-own-scans"])),
    user_service: UserService = Depends(get_user_service),
    service: FileService = Depends(get_file_service),
):
    user_id = _current_user_id(payload, user_service)
    response = service.get_project_priority_distribution(
        user_id=user_id,
        project_id=project_id,
    )
    return ApiResponse.success(data=response.model_dump(), meta=ResponseMeta(project_id=project_id))


@router.get("/analytics/analyzed-trend")
def get_project_files_analyzed(
    project_id: uuid.UUID = Query(..., alias=PROJECT_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(require_permissions(["view-own-scans"])),
    user_service: UserService = Depends(get_user_service),
    service: FileService = Depends(get_file_service),
):
    user_id = _current_user_id(payload, user_service)
    response = service.get_project_files_analyzed(
        user_id=user_id,
        project_id=project_id,
    )
    return ApiResponse.success(data=response.model_dump(), meta=ResponseMeta(project_id=project_id))


@router.get("/{file_id:uuid}")
def get_file_details(
    file_id: uuid.UUID,
    include_summary: bool = Query(default=False, alias=INCLUDE_SUMMARY_QUERY_PARAM),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: FileService = Depends(get_file_service),
):
    response = service.get_file_details(
        _current_user_id(payload, user_service),
        file_id,
        include_summary=include_summary,
    )
    return ApiResponse.success(data=response.model_dump(), meta=ResponseMeta(scan_id=response.scan_id))
