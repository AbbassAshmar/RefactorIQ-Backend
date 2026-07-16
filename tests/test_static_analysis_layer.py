from __future__ import annotations

from pathlib import Path

from app.analysis.services.scan_engine.pipeline.layers.static_analysis_layer import StaticAnalysisLayer
from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector


def test_static_analysis_reads_absolute_path_and_preserves_relative_identity(tmp_path: Path) -> None:
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("def greet(name):\n    return f'Hello {name}'\n", encoding="utf-8")
    vector = MetricsVector(
        layer=StaticAnalysisLayer.LAYER_NAME,
        absolute_path=source,
        relative_path="src/main.py",
    )

    result = StaticAnalysisLayer().run(vector)[0]

    assert result.absolute_path == source.resolve()
    assert result.relative_path == "src/main.py"
    assert result.metrics["source_lines_of_code"] == 2
