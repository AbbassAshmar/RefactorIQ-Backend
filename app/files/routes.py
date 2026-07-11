from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.files.constants import INCLUDE_SUMMARY_QUERY_PARAM, SCAN_ID_QUERY_PARAM
from app.files.dependencies import get_file_service
from app.files.service import FileService
from app.schemas.auth import TokenPayload
from app.schemas.response import ResponseMeta
from app.users.services.service import UserService
from app.utils.response import ApiResponse


router = APIRouter(prefix="/files", tags=["Files"])


def _current_user_id(payload: TokenPayload, user_service: UserService) -> uuid.UUID:
    user_id = uuid.UUID(payload.sub)
    user_service.get_user(user_id)
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


@router.get("/{file_id}")
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
