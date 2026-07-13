"""Administrative routes for metrics spanning multiple business modules."""

from fastapi import APIRouter, Depends

from app.analytics.analytics_service import AnalyticsService
from app.analytics.dependencies import get_analytics_service
from app.auth.auth_dtos import TokenPayload
from app.core.route_dependencies import require_permissions
from app.utils.response import ApiResponse


router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])


@router.get("/kpis")
def get_admin_kpis(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
    _: TokenPayload = Depends(require_permissions(["view-analytics"])),
):
    return ApiResponse.success(data=analytics_service.get_kpis().model_dump())
