from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select

from app.analysis.repositories.scan_result_repository import ScanResultRepository
from app.analysis.services.scan_engine.pipeline.metrics_vector import LayerResult, MetricsVector
from app.models import CircularDependencyGroup, CircularDependencyMember, CoChangeEdge, DependencyEdge


def test_repository_groups_by_relative_path_and_stores_relationships_directly(db_session) -> None:
    scan_id = uuid.uuid4()
    source = Path("C:/scan/repository/src/a.py")
    target = Path("C:/scan/repository/src/b.py")
    result = LayerResult(
        vectors=[
            MetricsVector(
                layer="static_analysis",
                absolute_path=source,
                relative_path="src/a.py",
                metrics={"lines_of_code": 10},
            ),
            MetricsVector(
                layer="history_analysis",
                absolute_path=source,
                relative_path="src/a.py",
                metadata={"co_changed_files": ["src/b.py"]},
            ),
            MetricsVector(
                layer="architecture_analysis",
                absolute_path=target,
                relative_path="src/b.py",
            ),
            MetricsVector(
                layer="history_analysis",
                absolute_path=target,
                relative_path="src/b.py",
                metadata={"co_changed_files": ["src/a.py"]},
            ),
        ],
        metadata={
            "dependency_edges": [
                ["src/a.py", "src/b.py"],
                ["src/a.py", "src/b.py"],
                ["src/b.py", "src/a.py"],
                ["src/a.py", "src/a.py"],
                ["src/a.py"],
            ],
            "circular_dependency_groups": [
                {"nodes": ["src/a.py", "src/b.py", "src/a.py", "unknown.py"]},
            ],
        },
    )

    records = ScanResultRepository(db_session).store_results(
        scan_id,
        ["src/a.py", "src/b.py", "src/missing.py"],
        result,
    )

    assert [record.file_path for record in records] == ["src/a.py", "src/b.py", "src/missing.py"]
    assert records[0].metrics["static_analysis"]["lines_of_code"] == 10
    assert len(db_session.scalars(select(DependencyEdge)).all()) == 2
    assert len(db_session.scalars(select(CoChangeEdge)).all()) == 1

    [group] = db_session.scalars(select(CircularDependencyGroup)).all()
    assert group.size == 2
    assert len(db_session.scalars(select(CircularDependencyMember)).all()) == 2
