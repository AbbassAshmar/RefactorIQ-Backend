from __future__ import annotations

from app.core.enums import ScanStatus, UserRole
from app.models import Project, Role, Scan, User
from app.scans.scans_repository import ScanRepository


def test_scan_status_updates_started_and_finished_timestamps(db_session):
    role = Role(name=UserRole.CLIENT)
    user = User(email='scan-status@example.com', username='scan-status', role=role)
    project = Project(
        name='Status project',
        repo_owner='owner',
        repo_name='repository',
        branch='main',
        user=user,
    )
    scan = Scan(project=project)
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)

    repository = ScanRepository(db_session)
    running = repository.update_scan_status(scan.id, ScanStatus.RUNNING)
    assert running.status == ScanStatus.RUNNING.value
    assert running.started_at is not None
    assert running.finished_at is None

    succeeded = repository.update_scan_status(scan.id, ScanStatus.SUCCEEDED)
    assert succeeded.status == ScanStatus.SUCCEEDED.value
    assert succeeded.finished_at is not None
