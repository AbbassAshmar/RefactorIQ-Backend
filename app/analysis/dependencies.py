from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Depends
from sqlalchemy.orm import Session

from app.analysis.services.scan_engine.pipeline.scan_workspace import (
    ScanWorkspaceService,
)
from app.analysis.services.scan_engine.scan_engine import ScanEngineService
from app.config import settings
from app.core.database import SessionLocal
from app.dependencies import (
    build_role_repository,
    build_scans_queue_service,
    build_user_repository,
    build_user_service,
)
from app.github.dependencies import get_github_service
from app.github.services.client_service import GithubClientService
from app.github.services.service import GithubService
from app.scans.repositories.scan_repository import ScanRepository
from app.scans.services.scan_service import ScanService
from app.scans.dependencies import get_scan_service

from app.analysis.services.scan_engine.pipeline.layers.architecture_analysis_layer import ArchitectureAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.decision_analysis_layer import DecisionAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.history_analysis_layer import HistoryAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.duplication_analysis_layer import DuplicationAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.static_analysis_layer import StaticAnalysisLayer
from app.analysis.services.scan_engine.pipeline.scan_pipeline import ScanPipeline


def get_scan_workspace_service() -> ScanWorkspaceService:
    return build_scan_workspace_service()


def build_scan_workspace_service() -> ScanWorkspaceService:
    base_dir = settings.SCAN_REPO_BASE_DIR
    return ScanWorkspaceService(base_dir)

def get_static_analysis_layer() -> StaticAnalysisLayer:
    return StaticAnalysisLayer()

def get_history_analysis_layer() -> HistoryAnalysisLayer:
    return HistoryAnalysisLayer()

def get_duplication_analysis_layer() -> DuplicationAnalysisLayer:
    return DuplicationAnalysisLayer()

def get_architecture_analysis_layer() -> ArchitectureAnalysisLayer:
    return ArchitectureAnalysisLayer()

def get_decision_analysis_layer() -> DecisionAnalysisLayer: 
    return DecisionAnalysisLayer()

def get_scan_pipeline(
    static_layer: StaticAnalysisLayer = Depends(get_static_analysis_layer),
    history_layer: HistoryAnalysisLayer = Depends(get_history_analysis_layer),
    duplication_layer: DuplicationAnalysisLayer = Depends(get_duplication_analysis_layer),
    architectural_layer: ArchitectureAnalysisLayer = Depends(get_architecture_analysis_layer),
    decision_layer: DecisionAnalysisLayer = Depends(get_decision_analysis_layer),
) -> ScanPipeline:
    return ScanPipeline(
        static_layer=static_layer,
        history_layer=history_layer,
        duplication_layer=duplication_layer,
        architectural_layer=architectural_layer,
        decision_layer=decision_layer,
    )

def get_scan_engine_service(
    scan_service: ScanService = Depends(get_scan_service),
    workspace_service: ScanWorkspaceService = Depends(get_scan_workspace_service),
    github_service: GithubService = Depends(get_github_service),
    scan_pipeline: ScanPipeline = Depends(get_scan_pipeline),
) -> ScanEngineService:
    return ScanEngineService(
        scan_service=scan_service,
        github_service=github_service, 
        workspace_service=workspace_service,
        scan_pipeline=scan_pipeline,
    )


def build_scan_pipeline() -> ScanPipeline:
    static_layer = StaticAnalysisLayer()
    history_layer = HistoryAnalysisLayer()
    duplication_layer = DuplicationAnalysisLayer()
    architectural_layer = ArchitectureAnalysisLayer()
    decision_layer = DecisionAnalysisLayer()

    return ScanPipeline(
        static_layer=static_layer,
        history_layer=history_layer,
        duplication_layer=duplication_layer,
        architectural_layer=architectural_layer,
        decision_layer=decision_layer,
    )

def build_scan_engine_service(db: Session) -> ScanEngineService:
    scan_repository = ScanRepository(db)
    scan_queue_service = build_scans_queue_service()
    scan_service = ScanService(scan_repository, scan_queue_service)

    user_repository = build_user_repository(db)
    role_repository = build_role_repository(db)
    user_service = build_user_service(user_repository, role_repository)

    github_client = GithubClientService()
    github_service = GithubService(github_client, user_service)

    return ScanEngineService(
        scan_service=scan_service,
        github_service=github_service,
        workspace_service=build_scan_workspace_service(),
        scan_pipeline=build_scan_pipeline(),
    )


@contextmanager
def provide_scan_engine_service() -> Iterator[ScanEngineService]:
    db = SessionLocal()
    try:
        yield build_scan_engine_service(db)
    finally:
        db.close()
