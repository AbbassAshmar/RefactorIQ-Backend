from __future__ import annotations

from pathlib import Path

from app.analysis.services.scan_engine.pipeline.layers.architecture_analysis_layer import ArchitectureAnalysisLayer


def test_architecture_layer_computes_fan_metrics_and_transitive_dependents(tmp_path: Path) -> None:
    _mark_repo_root(tmp_path)
    consumer = _write(tmp_path, "src/pkg/consumer.py", "from pkg import service\n")
    service = _write(tmp_path, "src/pkg/service.py", "from pkg import util\n")
    util = _write(tmp_path, "src/pkg/util.py", "VALUE = 1\n")

    vectors = ArchitectureAnalysisLayer().run([consumer, service, util])
    by_node = {vector.metadata["node"]: vector for vector in vectors}

    consumer_vector = by_node["/src/pkg/consumer.py"]
    service_vector = by_node["/src/pkg/service.py"]
    util_vector = by_node["/src/pkg/util.py"]

    assert consumer_vector.metrics["fan_in"] == 0
    assert consumer_vector.metrics["fan_out"] == 1
    assert consumer_vector.metrics["transitive_dependents_count"] == 0
    assert consumer_vector.metrics["instability_index"] == 1.0

    assert service_vector.metrics["fan_in"] == 1
    assert service_vector.metrics["fan_out"] == 1
    assert service_vector.metrics["transitive_dependents_count"] == 1
    assert service_vector.metrics["instability_index"] == 0.5

    assert util_vector.metrics["fan_in"] == 1
    assert util_vector.metrics["fan_out"] == 0
    assert util_vector.metrics["transitive_dependents_count"] == 2
    assert util_vector.metrics["instability_index"] == 0.0


def test_architecture_layer_reports_scc_metadata_and_circular_dependency_size(tmp_path: Path) -> None:
    _mark_repo_root(tmp_path)
    a = _write(tmp_path, "src/pkg/a.py", "from pkg import b\n")
    b = _write(tmp_path, "src/pkg/b.py", "from . import c\n")
    c = _write(tmp_path, "src/pkg/c.py", "from pkg import a\n")

    vectors = ArchitectureAnalysisLayer().run([a, b, c])

    for vector in vectors:
        assert vector.metrics["circular_dependency_size"] == 3
        assert vector.metadata["sccs"] == [
            {
                "nodes": ["/src/pkg/a.py", "/src/pkg/b.py", "/src/pkg/c.py"],
                "edges": [
                    ["/src/pkg/a.py", "/src/pkg/b.py"],
                    ["/src/pkg/b.py", "/src/pkg/c.py"],
                    ["/src/pkg/c.py", "/src/pkg/a.py"],
                ],
            }
        ]


def test_architecture_layer_ignores_external_imports(tmp_path: Path) -> None:
    _mark_repo_root(tmp_path)
    module = _write(tmp_path, "src/pkg/module.py", "import os\nimport missing_package\n")

    vector = ArchitectureAnalysisLayer().run([module])[0]

    assert vector.errors == []
    assert vector.metrics["fan_in"] == 0
    assert vector.metrics["fan_out"] == 0
    assert vector.metadata["sccs"] == []


def _mark_repo_root(path: Path) -> None:
    (path / ".git").mkdir()


def _write(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path
