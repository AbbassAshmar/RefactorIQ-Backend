from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.files.files_dtos import CircularDependencyRow, FileDetailRow, FileListRow, FileRelationshipRow
from app.files.files_service import FileService


class FakeFileRepository:
    def __init__(self) -> None:
        self.scan_id = uuid.uuid4()
        self.file = FileDetailRow(
            id=uuid.uuid4(),
            scan_id=self.scan_id,
            file_path='src/core/service.py',
            refactor_score=0.78,
            priority_band='high',
            metrics={
                'architecture_analysis': {'fan_in': 4, 'fan_out': 2},
                'decision_analysis': {'score_confidence': 0.9},
            },
            metadata={},
            errors={},
            created_at=datetime.now(timezone.utc),
            scan_finished_at=datetime.now(timezone.utc),
        )
        self.dependency = FileRelationshipRow(
            id=uuid.uuid4(),
            file_path='src/core/dependency.py',
            priority_band='medium',
            metrics={'architecture_analysis': {'fan_in': 1}},
            relationship='dependency',
            direction='outgoing',
        )

    def list_by_scan(self, user_id, scan_id):
        return [FileListRow(self.file.id, self.file.file_path, self.file.priority_band)]

    def get_details(self, user_id, file_id):
        return self.file

    def list_dependencies(self, scan_id, file_id):
        return [self.dependency]

    def list_co_changed_files(self, scan_id, file_id):
        return []

    def list_circular_dependencies(self, scan_id, file_id):
        return [CircularDependencyRow(uuid.uuid4(), 1, [FileListRow(self.file.id, self.file.file_path, 'high')])]

    def references_by_paths(self, scan_id, file_paths):
        return {}


class FakeSummaryProvider:
    def __init__(self) -> None:
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return 'Generated summary'


def test_file_service_returns_minimal_scan_file_list():
    repository = FakeFileRepository()
    service = FileService(repository, FakeSummaryProvider())

    response = service.list_scan_files(uuid.uuid4(), repository.scan_id)

    assert response.scan_id == repository.scan_id
    assert response.files[0].model_dump() == {
        'id': repository.file.id,
        'file_path': 'src/core/service.py',
        'priority_band': 'high',
    }


def test_file_details_only_generate_summaries_when_requested():
    repository = FakeFileRepository()
    provider = FakeSummaryProvider()
    service = FileService(repository, provider)

    without_summary = service.get_file_details(uuid.uuid4(), repository.file.id)
    assert without_summary.summaries is None
    assert provider.prompts == []

    with_summary = service.get_file_details(uuid.uuid4(), repository.file.id, include_summary=True)
    assert with_summary.summaries.general == 'Generated summary'
    assert with_summary.summaries.architectural == 'Generated summary'
    assert len(provider.prompts) == 2
    assert with_summary.dependencies[0].metrics['architecture_analysis']['fan_in'] == 1
