from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.scan_visualization.dependencies import get_scan_visualization_service
from app.scan_visualization.service import ScanVisualizationService
from app.utils.response import ApiResponse


router = APIRouter(prefix="/scan-visualization", tags=["Scan Visualization"])


@router.get("/runs")
def list_visualization_runs(
    limit: int = Query(default=25, ge=1, le=100),
    service: ScanVisualizationService = Depends(get_scan_visualization_service),
):
    runs = service.list_runs(limit=limit)
    return ApiResponse.success(data={"runs": [run.model_dump() for run in runs]})


@router.get("/runs/latest")
def get_latest_visualization_run(
    service: ScanVisualizationService = Depends(get_scan_visualization_service),
):
    snapshot = service.latest_snapshot()
    return ApiResponse.success(data={"snapshot": snapshot.model_dump()})


@router.get("/runs/{scan_id}")
def get_visualization_run(
    scan_id: uuid.UUID,
    service: ScanVisualizationService = Depends(get_scan_visualization_service),
):
    snapshot = service.snapshot(scan_id)
    return ApiResponse.success(data={"snapshot": snapshot.model_dump()})
