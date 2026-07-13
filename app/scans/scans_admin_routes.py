"""Administrative scan records and analytics owned by the scans module."""

import math
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.auth.auth_dtos import TokenPayload
from app.core.common_dtos import PaginationMeta, ResponseMeta
from app.core.enums import ScanStatus
from app.core.route_dependencies import require_permissions
from app.scans.dependencies import get_scan_service
from app.scans.scans_dtos import AdminScanListFilters
from app.scans.scans_service import ScanService
from app.utils.response import ApiResponse


analytics_router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])
admin_scans_router = APIRouter(prefix="/admin/scans", tags=["Admin Scans"])
router = analytics_router


@analytics_router.get("/scans-over-time")
def get_scans_over_time(
    project_id: uuid.UUID | None = None,
    scan_service: ScanService = Depends(get_scan_service),
    _: TokenPayload = Depends(require_permissions(["view-analytics"])),
):
    return ApiResponse.success(
        data=scan_service.get_scans_over_time(project_id=project_id).model_dump()
    )


@analytics_router.get("/scan-status-distribution")
def get_scan_status_distribution(
    scan_service: ScanService = Depends(get_scan_service),
    _: TokenPayload = Depends(require_permissions(["view-analytics"])),
):
    return ApiResponse.success(
        data=scan_service.get_scan_status_distribution().model_dump()
    )


@analytics_router.get("/failed-scans")
def list_failed_scans(
    limit: int = Query(default=5, ge=1, le=100),
    scan_service: ScanService = Depends(get_scan_service),
    _: TokenPayload = Depends(require_permissions(["view-analytics"])),
):
    scans = scan_service.list_failed_scans(limit=limit)
    return ApiResponse.success(
        data={"scans": [scan.model_dump() for scan in scans]}
    )


@admin_scans_router.get("")
def list_admin_scans(
    project_id: uuid.UUID | None = None,
    status: ScanStatus | None = None,
    sort: Literal["date_desc", "date_asc"] = "date_desc",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    scan_service: ScanService = Depends(get_scan_service),
    _: TokenPayload = Depends(require_permissions(["manage-scans"])),
):
    result = scan_service.list_admin_scans(
        AdminScanListFilters(
            project_id=project_id,
            status=status,
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
