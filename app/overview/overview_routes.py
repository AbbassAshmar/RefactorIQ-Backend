from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.core.route_dependencies import get_current_payload
from app.dependencies import get_user_service
from app.auth.auth_dtos import TokenPayload
from app.core.common_dtos import ResponseMeta
from app.core.constants import SCAN_ID_QUERY_PARAM
from app.overview.dependencies import get_overview_service
from app.overview.overview_service import OverviewService
from app.users.users_service import UserService
from app.utils.response import ApiResponse


router = APIRouter(prefix="/overview", tags=["Overview"])


def _user_id(payload: TokenPayload, user_service: UserService) -> uuid.UUID:
    user_id = uuid.UUID(payload.sub)
    user_service.get_user(user_id)
    return user_id


@router.get("/risk-trend")
def get_risk_trend(
    scan_id: uuid.UUID = Query(..., alias=SCAN_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: OverviewService = Depends(get_overview_service),
):
    response = service.risk_trend(_user_id(payload, user_service), scan_id)
    return ApiResponse.success(
        data=response.model_dump(),
        meta=ResponseMeta(scan_id=scan_id),
    )


@router.get("/scan-summary")
def get_scan_summary(
    scan_id: uuid.UUID = Query(..., alias=SCAN_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: OverviewService = Depends(get_overview_service),
):
    response = service.scan_summary(_user_id(payload, user_service), scan_id)
    return ApiResponse.success(
        data=response.model_dump(),
        meta=ResponseMeta(scan_id=scan_id),
    )


@router.get("/top-files")
def get_top_refactor_files(
    scan_id: uuid.UUID = Query(..., alias=SCAN_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: OverviewService = Depends(get_overview_service),
):
    response = service.top_refactor_files(_user_id(payload, user_service), scan_id)
    return ApiResponse.success(
        data=response.model_dump(),
        meta=ResponseMeta(scan_id=scan_id),
    )


@router.get("/risk-by-directory")
def get_risk_by_directory(
    scan_id: uuid.UUID = Query(..., alias=SCAN_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: OverviewService = Depends(get_overview_service),
):
    response = service.risk_by_directory(_user_id(payload, user_service), scan_id)
    return ApiResponse.success(
        data=response.model_dump(),
        meta=ResponseMeta(scan_id=scan_id),
    )


@router.get("/directory-insight")
def get_directory_insight(
    scan_id: uuid.UUID = Query(..., alias=SCAN_ID_QUERY_PARAM),
    payload: TokenPayload = Depends(get_current_payload),
    user_service: UserService = Depends(get_user_service),
    service: OverviewService = Depends(get_overview_service),
):
    response = service.directory_insight(_user_id(payload, user_service), scan_id)
    return ApiResponse.success(
        data=response.model_dump(),
        meta=ResponseMeta(scan_id=scan_id),
    )
