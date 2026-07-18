from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.services.scan_engine.pipeline.layers.decision_analysis_layer import (
    DecisionAnalysisLayer,
)
from app.analysis.services.scan_engine.pipeline.metrics_vector import LayerResult, MetricsVector


def _run_decision_file(
    layer: DecisionAnalysisLayer,
    relative_path: str,
    metrics_by_layer: dict[str, dict[str, int | float | None]],
) -> MetricsVector:
    absolute_path = Path("/workspace") / relative_path
    result = LayerResult(
        vectors=[
            MetricsVector(
                layer=layer_name,
                absolute_path=absolute_path,
                relative_path=relative_path,
                metrics=metrics,
            )
            for layer_name, metrics in metrics_by_layer.items()
        ]
    )
    return layer.run(result)[0]


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
                "runtime_circular_dependency_size": 4,
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
                "runtime_circular_dependency_size": 0,
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
    assert by_file["src/hot.py"].metadata["priority_band"] == "critical"

    assert summary.metrics["files_scored_count"] == 2
    assert summary.metrics["critical_priority_files_count"] == 1
    assert summary.metrics["max_refactor_score"] == hot_score
    assert summary.metadata["top_refactor_candidates"][0]["file_path"] == "src/hot.py"


def test_decision_layer_computes_each_component_once_per_file(monkeypatch: pytest.MonkeyPatch) -> None:
    layer = DecisionAnalysisLayer()
    weighted_score_calls = {
        "complexity": 0,
        "history": 0,
        "duplication": 0,
        "architecture": 0,
        "components": 0,
    }
    weight_groups = {
        "complexity": layer.complexity_metric_weights,
        "history": layer.history_metric_weights,
        "duplication": layer.duplication_metric_weights,
        "architecture": layer.architecture_metric_weights,
        "components": layer.component_weights,
    }
    original_weighted_score = layer._weighted_score

    def counting_weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
        group_name = next(name for name, group in weight_groups.items() if weights is group)
        weighted_score_calls[group_name] += 1
        return original_weighted_score(scores, weights)

    monkeypatch.setattr(layer, "_weighted_score", counting_weighted_score)

    _run_decision_file(
        layer,
        "src/cached.py",
        {
            "static_analysis": {
                "max_cyclomatic_complexity": 8,
                "max_cognitive_complexity": 12,
                "average_cyclomatic_complexity": 3,
                "average_cognitive_complexity": 4,
                "lines_of_code": 200,
                "source_lines_of_code": 160,
                "logical_lines_of_code": 120,
                "long_conditions_count": 1,
                "max_if_else_chain_length": 2,
                "average_parameters_count": 3,
                "count_of_fixme_comments": 0,
                "count_of_empty_except_blocks": 0,
                "testing_coverage": 70,
            },
            "history_analysis": {
                "update_count": 5,
                "recent_update_count": 2,
                "churn_to_size_ratio": 1.5,
                "bug_fix_ratio": 0.25,
                "bug_fix_commit_count": 1,
                "cyclomatic_complexity_growth_rate": 1,
                "co_change_file_count": 3,
                "contributors_count": 2,
            },
            "duplication_analysis": {
                "duplicate_loc_count": 20,
                "duplicate_blocks_count": 2,
                "semantic_duplicate_blocks_count": 1,
                "duplication_group_size": 2,
                "duplicate_file_candidates_count": 2,
                "max_similarity_score": 0.9,
            },
            "architecture_analysis": {
                "fan_in": 3,
                "fan_out": 4,
                "transitive_dependents_count": 8,
                    "betweenness_centrality": 0.01,
                    "circular_dependency_size": 0,
                    "runtime_circular_dependency_size": 0,
                    "instability_index": 0.57,
            },
        },
    )

    assert weighted_score_calls == {
        "complexity": 1,
        "history": 1,
        "duplication": 1,
        "architecture": 1,
        "components": 1,
    }


def test_duplication_materiality_prevents_tiny_clone_counts_from_dominating() -> None:
    layer = DecisionAnalysisLayer()

    def score_file(relative_path: str, loc: int, scale: int) -> MetricsVector:
        return _run_decision_file(
            layer,
            relative_path,
            {
                "static_analysis": {
                    "max_cyclomatic_complexity": 0,
                    "max_cognitive_complexity": 0,
                    "average_cyclomatic_complexity": 0,
                    "average_cognitive_complexity": 0,
                    "logical_lines_of_code": loc,
                    "lines_of_code": loc,
                    "source_lines_of_code": loc,
                    "long_conditions_count": scale,
                    "max_if_else_chain_length": 0,
                    "average_parameters_count": 0,
                    "count_of_fixme_comments": scale,
                    "count_of_empty_except_blocks": scale,
                    "testing_coverage": 100,
                },
                "duplication_analysis": {
                    "duplicate_loc_count": 20 * scale,
                    "duplicate_blocks_count": scale,
                    "semantic_duplicate_blocks_count": scale,
                    "duplication_group_size": 3,
                    "duplicate_file_candidates_count": scale,
                    "max_similarity_score": 0.9,
                },
            },
        )

    small_file = score_file("src/small.py", loc=100, scale=1)
    large_file = score_file("src/large.py", loc=1_000, scale=10)

    assert large_file.metrics["duplication_score"] > small_file.metrics["duplication_score"]
    assert small_file.metrics["duplication_score"] < 0.4
    assert (
        large_file.metrics["complexity_score"] - small_file.metrics["complexity_score"]
    ) == pytest.approx(0.12)
    assert small_file.metadata["count_density_reference_loc"] == 500.0
    assert small_file.metadata["scoring_model_version"] == 4


def test_architecture_score_omits_deterministic_dependency_total() -> None:
    layer = DecisionAnalysisLayer()

    assert "dependency_total" not in layer.architecture_metric_weights
    assert sum(layer.architecture_metric_weights.values()) == pytest.approx(1.0)


def test_weighted_score_rejects_score_and_weight_key_drift() -> None:
    layer = DecisionAnalysisLayer()

    with pytest.raises(ValueError, match="missing scores"):
        layer._weighted_score({"first": 1.0}, {"first": 0.5, "second": 0.5})

    with pytest.raises(ValueError, match="unexpected scores"):
        layer._weighted_score({"first": 1.0, "second": 0.0}, {"first": 1.0})

    with pytest.raises(ValueError, match="sum to 1.0"):
        layer._weighted_score({"first": 1.0}, {"first": 0.5})


def test_component_failure_is_not_recomputed_through_refactor_score() -> None:
    layer = DecisionAnalysisLayer()
    layer.complexity_metric_weights.pop("size")

    vector = _run_decision_file(
        layer,
        "src/broken-config.py",
        {"static_analysis": {"logical_lines_of_code": 100}},
    )

    assert vector.metrics["complexity_score"] is None
    assert vector.metrics["refactor_score"] is None
    assert len(vector.errors) == 1
    assert vector.errors[0].startswith("complexity_score failed:")


def test_known_fixture_hotspots_cross_calibrated_priority_bands() -> None:
    layer = DecisionAnalysisLayer()
    tower = _run_decision_file(
        layer,
        "src/nimbus_ops/application/services/operational_control_tower.py",
        {
            "static_analysis": {
                "lines_of_code": 323,
                "source_lines_of_code": 257,
                "logical_lines_of_code": 208,
                "max_cyclomatic_complexity": 29,
                "max_cognitive_complexity": 64,
                "average_cyclomatic_complexity": 5.846,
                "average_cognitive_complexity": 8.643,
                "long_conditions_count": 1,
                "max_if_else_chain_length": 4,
                "average_parameters_count": 3,
                "count_of_fixme_comments": 0,
                "count_of_empty_except_blocks": 0,
                "testing_coverage": 0,
            },
            "history_analysis": {
                "update_count": 1,
                "recent_update_count": 1,
                "churn_to_size_ratio": 1.0,
                "bug_fix_ratio": 0.0,
                "bug_fix_commit_count": 0,
                "cyclomatic_complexity_growth_rate": 0,
                "co_change_file_count": 0,
                "contributors_count": 1,
            },
            "duplication_analysis": {
                "duplicate_loc_count": 3,
                "duplicate_blocks_count": 1,
                "semantic_duplicate_blocks_count": 0,
                "duplication_group_size": 2,
                "duplicate_file_candidates_count": 1,
                "max_similarity_score": 0.0,
            },
            "architecture_analysis": {
                "fan_in": 10,
                "fan_out": 5,
                "transitive_dependents_count": 36,
                "betweenness_centrality": 0.024692,
                "circular_dependency_size": 11,
                "runtime_circular_dependency_size": 0,
                "instability_index": 0.333,
            },
        },
    )
    exporter = _run_decision_file(
        layer,
        "src/nimbus_ops/infrastructure/legacy_operations_exporter.py",
        {
            "static_analysis": {
                "lines_of_code": 125,
                "source_lines_of_code": 103,
                "logical_lines_of_code": 49,
                "max_cyclomatic_complexity": 19,
                "max_cognitive_complexity": 15,
                "average_cyclomatic_complexity": 7,
                "average_cognitive_complexity": 4.167,
                "long_conditions_count": 0,
                "max_if_else_chain_length": 1,
                "average_parameters_count": 3,
                "count_of_fixme_comments": 0,
                "count_of_empty_except_blocks": 0,
                "testing_coverage": 0,
            },
            "history_analysis": {
                "update_count": 1,
                "recent_update_count": 1,
                "churn_to_size_ratio": 1.0,
                "bug_fix_ratio": 0.0,
                "bug_fix_commit_count": 0,
                "cyclomatic_complexity_growth_rate": 0,
                "co_change_file_count": 0,
                "contributors_count": 1,
            },
            "duplication_analysis": {
                "duplicate_loc_count": 3,
                "duplicate_blocks_count": 1,
                "semantic_duplicate_blocks_count": 0,
                "duplication_group_size": 2,
                "duplicate_file_candidates_count": 1,
                "max_similarity_score": 0.0,
            },
            "architecture_analysis": {
                "fan_in": 1,
                "fan_out": 2,
                "transitive_dependents_count": 15,
                "betweenness_centrality": 0.000026,
                "circular_dependency_size": 0,
                "runtime_circular_dependency_size": 0,
                "instability_index": 0.667,
            },
        },
    )

    assert tower.metadata["priority_band"] == "high"
    assert exporter.metadata["priority_band"] == "medium"
    assert tower.metrics["refactor_score"] > exporter.metrics["refactor_score"]


def test_unavailable_inputs_are_unscored_instead_of_low_risk() -> None:
    layer = DecisionAnalysisLayer()
    unavailable = _run_decision_file(
        layer,
        "src/unavailable.py",
        {
            "history_analysis": {
                metric_name: None
                for metric_name in (
                    "contributors_count",
                    "update_count",
                    "recent_update_count",
                    "churn_to_size_ratio",
                    "bug_fix_commit_count",
                    "bug_fix_ratio",
                    "cyclomatic_complexity_growth_rate",
                    "co_change_file_count",
                )
            }
        },
    )
    scored = MetricsVector(
        layer=layer.LAYER_NAME,
        absolute_path=Path("/workspace/src/scored.py"),
        relative_path="src/scored.py",
        metrics={"refactor_score": 0.5},
    )
    summary = layer.summarize(
        LayerResult(vectors=[unavailable, scored])
    )[0]

    assert unavailable.metrics["refactor_score"] is None
    assert unavailable.metadata["priority_band"] is None
    assert unavailable.metrics["score_confidence"] == 0.0
    assert summary.metrics["files_evaluated_count"] == 2
    assert summary.metrics["files_scored_count"] == 1
    assert summary.metrics["unscored_files_count"] == 1
    assert summary.metrics["average_refactor_score"] == 0.5


def test_semantic_metric_failure_renormalizes_duplication_with_lower_confidence() -> None:
    layer = DecisionAnalysisLayer()
    vector = _run_decision_file(
        layer,
        "src/partial-duplication.py",
        {
            "static_analysis": {
                "lines_of_code": 100,
                "source_lines_of_code": 80,
                "logical_lines_of_code": 50,
            },
            "duplication_analysis": {
                "duplicate_loc_count": 30,
                "duplicate_blocks_count": 3,
                "semantic_duplicate_blocks_count": None,
                "duplication_group_size": 3,
                "duplicate_file_candidates_count": 2,
                "max_similarity_score": None,
            },
        },
    )

    assert vector.metrics["duplication_score"] is not None
    assert vector.metadata["component_metric_coverage"]["duplication_score"] == pytest.approx(0.68)
    assert 0.0 < vector.metrics["score_confidence"] < 1.0


def test_priority_threshold_constants_drive_bands_and_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layer = DecisionAnalysisLayer()
    monkeypatch.setattr(layer, "CRITICAL_PRIORITY_THRESHOLD", 0.8)
    monkeypatch.setattr(layer, "HIGH_PRIORITY_THRESHOLD", 0.5)
    monkeypatch.setattr(layer, "MEDIUM_PRIORITY_THRESHOLD", 0.3)
    decision_result = LayerResult(
        vectors=[
            MetricsVector(
                layer=layer.LAYER_NAME,
                absolute_path=Path("/workspace/src/critical.py"),
                relative_path="src/critical.py",
                metrics={"refactor_score": 0.8},
            ),
            MetricsVector(
                layer=layer.LAYER_NAME,
                absolute_path=Path("/workspace/src/high.py"),
                relative_path="src/high.py",
                metrics={"refactor_score": 0.5},
            ),
            MetricsVector(
                layer=layer.LAYER_NAME,
                absolute_path=Path("/workspace/src/medium.py"),
                relative_path="src/medium.py",
                metrics={"refactor_score": 0.3},
            ),
            MetricsVector(
                layer=layer.LAYER_NAME,
                absolute_path=Path("/workspace/src/low.py"),
                relative_path="src/low.py",
                metrics={"refactor_score": 0.29},
            ),
        ]
    )

    summary = layer.summarize(decision_result)[0]

    assert layer._priority_band(0.8) == "critical"
    assert layer._priority_band(0.5) == "high"
    assert layer._priority_band(0.3) == "medium"
    assert layer._priority_band(0.29) == "low"
    assert summary.metrics["critical_priority_files_count"] == 1
    assert summary.metrics["high_priority_files_count"] == 1
    assert summary.metrics["medium_priority_files_count"] == 1
    assert summary.metrics["low_priority_files_count"] == 1
    assert sum(
        summary.metrics[key]
        for key in (
            "critical_priority_files_count",
            "high_priority_files_count",
            "medium_priority_files_count",
            "low_priority_files_count",
        )
    ) == summary.metrics["files_scored_count"]
    assert summary.metadata["priority_thresholds"] == {
        "critical": 0.8,
        "high": 0.5,
        "medium": 0.3,
    }
