from __future__ import annotations

from pathlib import Path

from app.analysis.services.scan_engine.pipeline.layers.decision_analysis_layer import (
    DecisionAnalysisLayer,
)
from app.analysis.services.scan_engine.pipeline.metrics_vector import LayerResult, MetricsVector


def test_decision_layer_scores_files_between_zero_and_one_and_ranks_pressure() -> None:
    vectors = [
        MetricsVector(
            layer="static_analysis",
            absolute_path=Path("/workspace/src/hot.py"),
            relative_path="src/hot.py",
            metrics={
                "max_cyclomatic_complexity": 18,
                "average_cyclomatic_complexity": 7,
                "max_cognitive_complexity": 28,
                "average_cognitive_complexity": 12,
                "logical_lines_of_code": 420,
                "lines_of_code": 520,
                "long_conditions_count": 4,
                "max_if_else_chain_length": 5,
                "average_parameters_count": 6,
                "count_of_fixme_comments": 4,
                "count_of_empty_except_blocks": 2,
                "testing_coverage": 20.0,
            },
        ),
        MetricsVector(
            layer="history_analysis",
            absolute_path=Path("/workspace/src/hot.py"),
            relative_path="src/hot.py",
            metrics={
                "recent_update_count": 10,
                "churn_to_size_ratio": 7.0,
                "bug_fix_ratio": 0.4,
                "bug_fix_commit_count": 5,
                "cyclomatic_complexity_growth_rate": 4,
                "co_change_file_count": 10,
                "contributors_count": 4,
                "recent_to_lifetime_update_ratio": 0.7,
            },
        ),
        MetricsVector(
            layer="duplication_analysis",
            absolute_path=Path("/workspace/src/hot.py"),
            relative_path="src/hot.py",
            metrics={
                "duplicate_blocks_count": 4,
                "duplicate_loc_count": 120,
                "semantic_duplicate_blocks_count": 3,
                "duplication_group_size": 4,
                "duplicate_file_candidates_count": 4,
                "max_similarity_score": 0.95,
            },
        ),
        MetricsVector(
            layer="architecture_analysis",
            absolute_path=Path("/workspace/src/hot.py"),
            relative_path="src/hot.py",
            metrics={
                "fan_in": 8,
                "fan_out": 10,
                "transitive_dependents_count": 25,
                "betweenness_centrality": 0.7,
                "circular_dependency_size": 4,
                "instability_index": 0.8,
            },
        ),
        MetricsVector(
            layer="static_analysis",
            absolute_path=Path("/workspace/src/calm.py"),
            relative_path="src/calm.py",
            metrics={
                "max_cyclomatic_complexity": 2,
                "average_cyclomatic_complexity": 1,
                "max_cognitive_complexity": 2,
                "average_cognitive_complexity": 1,
                "logical_lines_of_code": 60,
                "lines_of_code": 75,
                "long_conditions_count": 0,
                "max_if_else_chain_length": 1,
                "average_parameters_count": 2,
                "count_of_fixme_comments": 0,
                "count_of_empty_except_blocks": 0,
                "testing_coverage": 95.0,
            },
        ),
        MetricsVector(
            layer="history_analysis",
            absolute_path=Path("/workspace/src/calm.py"),
            relative_path="src/calm.py",
            metrics={
                "recent_update_count": 1,
                "churn_to_size_ratio": 0.2,
                "bug_fix_ratio": 0.0,
                "bug_fix_commit_count": 0,
                "cyclomatic_complexity_growth_rate": 0,
                "co_change_file_count": 1,
                "contributors_count": 1,
                "recent_to_lifetime_update_ratio": 0.1,
            },
        ),
        MetricsVector(
            layer="duplication_analysis",
            absolute_path=Path("/workspace/src/calm.py"),
            relative_path="src/calm.py",
            metrics={
                "duplicate_blocks_count": 0,
                "duplicate_loc_count": 0,
                "semantic_duplicate_blocks_count": 0,
                "duplication_group_size": 0,
                "duplicate_file_candidates_count": 0,
                "max_similarity_score": 0.0,
            },
        ),
        MetricsVector(
            layer="architecture_analysis",
            absolute_path=Path("/workspace/src/calm.py"),
            relative_path="src/calm.py",
            metrics={
                "fan_in": 1,
                "fan_out": 1,
                "transitive_dependents_count": 0,
                "betweenness_centrality": 0.0,
                "circular_dependency_size": 0,
                "instability_index": 0.5,
            },
        ),
    ]

    layer = DecisionAnalysisLayer()
    file_decision_results = [
        layer.run(LayerResult(vectors=[vector for vector in vectors if vector.relative_path == "src/hot.py"])),
        layer.run(LayerResult(vectors=[vector for vector in vectors if vector.relative_path == "src/calm.py"])),
    ]
    decision_result = LayerResult(vectors=[result[0] for result in file_decision_results])
    summary = layer.summarize(decision_result)[0]
    by_file = {
        vector.relative_path: vector
        for vector in decision_result.vectors
        if vector.relative_path is not None
    }

    hot_score = by_file["src/hot.py"].metrics["refactor_score"]
    calm_score = by_file["src/calm.py"].metrics["refactor_score"]

    assert 0.0 <= calm_score <= 1.0
    assert 0.0 <= hot_score <= 1.0
    assert hot_score > calm_score
    assert by_file["src/hot.py"].metadata["priority_band"] in {"medium", "high"}

    assert summary.metrics["files_scored_count"] == 2
    assert summary.metrics["max_refactor_score"] == hot_score
    assert summary.metadata["top_refactor_candidates"][0]["file_path"] == "src/hot.py"
