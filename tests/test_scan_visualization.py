from __future__ import annotations

import uuid

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector
from app.scan_visualization.repository import ScanVisualizationRepository
from app.scan_visualization.service import ScanVisualizationService


def test_scan_visualization_snapshot_groups_files_and_circular_metadata(db_session):
    scan_id = uuid.uuid4()
    repository = ScanVisualizationRepository(db_session)
    service = ScanVisualizationService(repository)

    repository.store_vectors(
        scan_id,
        [
            MetricsVector(
                layer="static_analysis",
                file_path="/src/a.py",
                metrics={"lines_of_code": 12},
            ),
            MetricsVector(
                layer="architecture_analysis",
                file_path="/src/a.py",
                metrics={"fan_in": 1},
                metadata={
                    "sccs": [
                        {
                            "nodes": ["/src/a.py", "/src/b.py"],
                            "edges": [["/src/a.py", "/src/b.py"]],
                        }
                    ]
                },
            ),
            MetricsVector(
                layer="decision_analysis",
                file_path=None,
                metrics={"files_scored_count": 1},
                metadata={"top_refactor_candidates": [{"file_path": "/src/a.py"}]},
            ),
        ],
    )

    snapshot = service.snapshot(scan_id)

    assert snapshot.scan_id == scan_id
    assert [file.file_path for file in snapshot.files] == ["/src/a.py"]
    assert [layer.layer for layer in snapshot.files[0].layers] == [
        "static_analysis",
        "architecture_analysis",
    ]
    assert [layer.layer for layer in snapshot.codebase_layers] == ["decision_analysis"]
    assert len(snapshot.circular_dependencies) == 1
    assert snapshot.circular_dependencies[0].nodes == ["/src/a.py", "/src/b.py"]


def test_scan_visualization_clear_scan_removes_previous_vectors(db_session):
    scan_id = uuid.uuid4()
    repository = ScanVisualizationRepository(db_session)

    repository.store_vectors(
        scan_id,
        [MetricsVector(layer="static_analysis", file_path="/src/a.py")],
    )
    repository.clear_scan(scan_id)

    assert repository.list_by_scan_id(scan_id) == []
