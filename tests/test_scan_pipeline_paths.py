from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.services.scan_engine.pipeline.layers.static_analysis_layer import StaticAnalysisLayer
from app.analysis.services.scan_engine.pipeline.scan_pipeline import ScanPipeline


def test_pipeline_prepares_canonical_paths_once_and_rejects_files_outside_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repository"
    source = repo_root / "src" / "main.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 2\n", encoding="utf-8")

    pipeline = ScanPipeline(static_layer=StaticAnalysisLayer())
    [vector] = pipeline._prepare_file_vectors([source], repo_root)

    assert vector.absolute_path == source.resolve()
    assert vector.relative_path == "src/main.py"

    with pytest.raises(ValueError, match="outside scan workspace"):
        pipeline._prepare_file_vectors([outside], repo_root)
