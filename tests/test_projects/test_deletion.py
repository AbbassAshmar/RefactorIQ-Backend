from __future__ import annotations

from unittest.mock import MagicMock

from app.analysis.services.scan_engine.pipeline.scan_workspace import ScanWorkspaceService
from app.core.enums import RefactorQueueStatus, ScanStatus, UserRole
from app.models import (
    Project,
    RefactorQueueItem,
    Role,
    Scan,
    ScanFile,
    ScanVisualizationRecord,
    User,
)
from app.projects.projects_repository import ProjectRepository
from app.projects.projects_service import ProjectService


def test_delete_project_stops_scans_cleans_workspaces_and_uses_cascades(
    db_session,
    tmp_path,
):
    role = Role(name=UserRole.CLIENT)
    user = User(email="delete@example.com", username="delete-owner", role=role)
    project = Project(
        name="Delete me",
        repo_owner="owner",
        repo_name="repo",
        branch="main",
        user=user,
    )
    pending_scan = Scan(project=project, status=ScanStatus.PENDING)
    succeeded_scan = Scan(project=project, status=ScanStatus.SUCCEEDED)
    db_session.add_all([project, pending_scan, succeeded_scan])
    db_session.flush()

    visualization = ScanVisualizationRecord(
        scan_id=pending_scan.id,
        layer="static_analysis",
        metrics={},
        errors=[],
        metadata_json={},
    )
    db_session.add_all(
        [
            visualization,
            ScanFile(
                scan_id=pending_scan.id,
                file_path="src/example.py",
                metrics={},
                metadata_json={},
                errors={},
            ),
            RefactorQueueItem(
                project_id=project.id,
                file_path="src/example.py",
                status=RefactorQueueStatus.PENDING,
                position=0,
            ),
        ]
    )
    db_session.commit()

    workspace_service = ScanWorkspaceService(tmp_path)
    for scan in (pending_scan, succeeded_scan):
        workspace_service.path_for(scan.id).mkdir(parents=True)

    scan_service = MagicMock()
    scan_service.request_scan_cancellations.return_value = {pending_scan.id: True}
    project_service = ProjectService(
        ProjectRepository(db_session),
        scan_service,
        workspace_service,
    )

    project_service.delete_project(project.id, user.id)

    db_session.expire_all()
    assert db_session.get(Project, project.id) is None
    assert db_session.get(Scan, pending_scan.id) is None
    assert db_session.get(Scan, succeeded_scan.id) is None
    assert db_session.get(ScanVisualizationRecord, visualization.id) is None
    assert db_session.query(ScanFile).count() == 0
    assert db_session.query(RefactorQueueItem).count() == 0
    assert not workspace_service.path_for(pending_scan.id).exists()
    assert not workspace_service.path_for(succeeded_scan.id).exists()

    scan_service.request_scan_cancellations.assert_called_once_with([pending_scan.id])
    forgotten_ids = set(scan_service.forget_scan_results.call_args.args[0])
    assert forgotten_ids == {pending_scan.id, succeeded_scan.id}
