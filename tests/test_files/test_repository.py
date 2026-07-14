from __future__ import annotations

import uuid

import pytest

from app.core.enums import ScanStatus, UserRole
from app.core.exceptions.repository_exceptions import RecordNotFoundException
from app.files.files_repository import FileRepository
from app.models import (
    CircularDependencyGroup,
    CircularDependencyMember,
    DependencyEdge,
    Project,
    Role,
    Scan,
    ScanFile,
    User,
)


def _successful_scan(db_session):
    role = Role(name=UserRole.CLIENT)
    user = User(
        email=f'{uuid.uuid4()}@example.com',
        username='dependency-owner',
        password='hashed',
        role=role,
    )
    project = Project(
        name='Dependency project',
        repo_owner='owner',
        repo_name=f'repo-{uuid.uuid4()}',
        branch='main',
        user=user,
    )
    scan = Scan(project=project, status=ScanStatus.SUCCEEDED)
    db_session.add(scan)
    db_session.flush()
    return user, scan


def test_repository_returns_all_nodes_sorted_edges_and_cycles(db_session):
    user, scan = _successful_scan(db_session)
    file_c = ScanFile(scan_id=scan.id, file_path='src/c.py', priority_band='low')
    file_a = ScanFile(scan_id=scan.id, file_path='src/a.py', priority_band='high')
    file_b = ScanFile(scan_id=scan.id, file_path='src/b.py', priority_band='medium')
    db_session.add_all([file_c, file_a, file_b])
    db_session.flush()
    db_session.add(DependencyEdge(scan_id=scan.id, source_file_id=file_b.id, target_file_id=file_a.id))
    group = CircularDependencyGroup(scan_id=scan.id, size=2)
    db_session.add(group)
    db_session.flush()
    db_session.add_all([
        CircularDependencyMember(group_id=group.id, file_id=file_b.id),
        CircularDependencyMember(group_id=group.id, file_id=file_a.id),
    ])
    db_session.commit()

    repository = FileRepository(db_session)
    nodes, edges = repository.list_scan_dependency_graph(user.id, scan.id)
    groups = repository.list_scan_circular_dependencies(user.id, scan.id)

    assert [node.file_path for node in nodes] == ['src/a.py', 'src/b.py', 'src/c.py']
    assert [(edge.source_file_id, edge.target_file_id) for edge in edges] == [(file_b.id, file_a.id)]
    assert len(groups) == 1
    assert [member.file_path for member in groups[0].members] == ['src/a.py', 'src/b.py']


def test_repository_rejects_inaccessible_unsuccessful_and_missing_scans(db_session):
    user, scan = _successful_scan(db_session)
    db_session.commit()

    repository = FileRepository(db_session)

    with pytest.raises(RecordNotFoundException):
        repository.list_scan_dependency_graph(uuid.uuid4(), scan.id)

    scan.status = ScanStatus.PENDING
    db_session.commit()
    with pytest.raises(RecordNotFoundException):
        repository.list_scan_circular_dependencies(user.id, scan.id)

    with pytest.raises(RecordNotFoundException):
        repository.list_scan_dependency_graph(user.id, uuid.uuid4())

    assert user.id is not None
