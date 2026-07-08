from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.analysis.services.scan_engine.pipeline.layers.duplication_analysis_layer import (
    DuplicationAnalysisLayer,
)


class IndexedEmbeddingService:
    model_id = "fake-indexed"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            [1.0 if index == dimension else 0.0 for dimension in range(len(texts))]
            for index, _ in enumerate(texts)
        ]


class SemanticPairEmbeddingService:
    model_id = "fake-semantic-pair"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            if "total_positive" in text or "sum_above_zero" in text:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


def test_duplication_layer_detects_token_normalized_syntax_duplicates(tmp_path: Path) -> None:
    _mark_repo_root(tmp_path)
    left = _write(
        tmp_path,
        "src/pkg/left.py",
        """
def normalize_names(names):
    result = []
    for name in names:
        result.append(name.strip().lower())
    return result
""",
    )
    right = _write(
        tmp_path,
        "src/pkg/right.py",
        """
def clean_labels(labels):
    output = []
    for label in labels:
        output.append(label.strip().lower())
    return output
""",
    )
    unrelated = _write(
        tmp_path,
        "src/pkg/unrelated.py",
        """
def multiply(value, factor):
    product = value * factor
    if product > 100:
        return product - 1
    return product
""",
    )

    layer = DuplicationAnalysisLayer(
        embedding_service=IndexedEmbeddingService(),
        semantic_similarity_threshold=0.99,
    )
    vectors = layer.run([left, right, unrelated])
    by_path = {Path(vector.file_path).resolve(): vector for vector in vectors}

    assert by_path[left].errors == []
    assert by_path[left].metrics["duplicate_blocks_count"] == 1
    assert by_path[left].metrics["duplicate_loc_count"] == 5
    assert by_path[left].metrics["duplication_group_size"] == 2
    assert by_path[left].metrics["semantic_duplicate_blocks_count"] == 0

    assert by_path[right].metrics["duplicate_blocks_count"] == 1
    assert by_path[unrelated].metrics["duplicate_blocks_count"] == 0


def test_duplication_layer_detects_semantic_duplicates_with_injected_embeddings(tmp_path: Path) -> None:
    _mark_repo_root(tmp_path)
    loop_sum = _write(
        tmp_path,
        "src/pkg/loop_sum.py",
        """
def total_positive(values):
    total = 0
    for value in values:
        if value > 0:
            total += value
    return total
""",
    )
    comprehension_sum = _write(
        tmp_path,
        "src/pkg/comprehension_sum.py",
        """
def sum_above_zero(items):
    positives = [item for item in items if item > 0]
    answer = sum(positives)
    return answer
""",
    )
    unrelated = _write(
        tmp_path,
        "src/pkg/unrelated.py",
        """
def render_title(title):
    cleaned = title.strip()
    heading = cleaned.title()
    return f"#{heading}"
""",
    )

    layer = DuplicationAnalysisLayer(
        embedding_service=SemanticPairEmbeddingService(),
        syntax_similarity_threshold=0.99,
        semantic_similarity_threshold=0.95,
    )
    vectors = layer.run([loop_sum, comprehension_sum, unrelated])
    by_path = {Path(vector.file_path).resolve(): vector for vector in vectors}

    assert by_path[loop_sum].errors == []
    assert by_path[loop_sum].metrics["duplicate_blocks_count"] == 0
    assert by_path[loop_sum].metrics["semantic_duplicate_blocks_count"] == 1
    assert by_path[loop_sum].metrics["max_similarity_score"] == 1.0
    assert by_path[loop_sum].metrics["duplicate_file_candidates_count"] == 1

    assert by_path[comprehension_sum].metrics["semantic_duplicate_blocks_count"] == 1
    assert by_path[unrelated].metrics["semantic_duplicate_blocks_count"] == 0


def _mark_repo_root(path: Path) -> None:
    (path / ".git").mkdir()


def _write(root: Path, relative_path: str, source: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source.strip() + "\n", encoding="utf-8")
    return path
