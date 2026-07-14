import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.analysis.services.scan_engine.pipeline.metrics_vector import LayerResult, MetricValue, MetricsVector

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DecisionAnalysisContext:
    absolute_path: Path
    relative_path: str
    result: LayerResult
    metrics: dict[str, MetricValue]
    available_layers: set[str]
    error_count: int
    none_metric_count: int
    component_cache: dict[str, float] = field(default_factory=dict)


MetricHandler = Callable[[DecisionAnalysisContext], int | float | str | bool | None]


class DecisionAnalysisLayer:
    """Layer 5 - per-file refactor priority scoring."""

    LAYER_NAME = "decision_analysis"
    SCORING_MODEL_VERSION = 2
    COUNT_DENSITY_REFERENCE_LOC = 500.0
    HIGH_PRIORITY_THRESHOLD = 0.75
    MEDIUM_PRIORITY_THRESHOLD = 0.45
    EXPECTED_INPUT_LAYERS = {
        "static_analysis",
        "history_analysis",
        "duplication_analysis",
        "architecture_analysis",
    }

    def __init__(self) -> None:
        self.component_weights: dict[str, float] = {
            "complexity_score": 0.30,
            "history_score": 0.25,
            "duplication_score": 0.25,
            "architecture_score": 0.20,
        }
        self.complexity_metric_weights: dict[str, float] = {
            "max_cyclomatic_complexity": 0.18,
            "max_cognitive_complexity": 0.18,
            "average_cyclomatic_complexity": 0.09,
            "average_cognitive_complexity": 0.09,
            "size": 0.12,
            "long_conditions_count": 0.08,
            "max_if_else_chain_length": 0.07,
            "average_parameters_count": 0.07,
            "count_of_fixme_comments": 0.06,
            "count_of_empty_except_blocks": 0.04,
            "testing_coverage_gap": 0.02,
        }
        self.history_metric_weights: dict[str, float] = {
            "churn_to_size_ratio": 0.25,
            "recent_update_count": 0.18,
            "bug_fix_ratio": 0.18,
            "cyclomatic_complexity_growth_rate": 0.12,
            "bug_fix_commit_count": 0.10,
            "co_change_file_count": 0.10,
            "contributors_count": 0.04,
            "recent_to_lifetime_update_ratio": 0.03,
        }
        self.duplication_metric_weights: dict[str, float] = {
            "duplicate_loc_ratio": 0.24,
            "duplicate_blocks_count": 0.22,
            "semantic_duplicate_blocks_count": 0.22,
            "duplication_group_size": 0.12,
            "duplicate_file_candidates_count": 0.10,
            "max_similarity_score": 0.10,
        }
        self.architecture_metric_weights: dict[str, float] = {
            # Renormalized after removing dependency_total, which is exactly
            # fan_in + fan_out. Instability remains as a direction signal.
            "circular_dependency_size": 0.24 / 0.96,
            "betweenness_centrality": 0.20 / 0.96,
            "transitive_dependents_count": 0.18 / 0.96,
            "fan_out": 0.16 / 0.96,
            "fan_in": 0.12 / 0.96,
            "instability_index": 0.06 / 0.96,
        }
        self.metric_handlers: dict[str, MetricHandler] = {
            "complexity_score": self.complexity_score,
            "history_score": self.history_score,
            "duplication_score": self.duplication_score,
            "architecture_score": self.architecture_score,
            "refactor_score": self.refactor_score,
            "score_confidence": self.score_confidence,
        }

    def run(self, result: LayerResult) -> LayerResult:
        logger.info("[DECISION] running decision analysis on %d vectors for one file", len(result.vectors))

        try:
            absolute_path, relative_path = self._paths_for(result)
            vector = MetricsVector(
                layer=self.LAYER_NAME,
                absolute_path=absolute_path,
                relative_path=relative_path,
            )
            context = self._build_context(absolute_path, relative_path, result)
            for metric_name, handler in self.metric_handlers.items():
                if metric_name == "refactor_score" and any(
                    vector.metrics.get(component_name) is None
                    for component_name in self.component_weights
                ):
                    vector.metrics[metric_name] = None
                    continue
                try:
                    vector.metrics[metric_name] = handler(context)
                except Exception as exc:
                    vector.errors.append(f"{metric_name} failed: {exc}")
                    vector.metrics[metric_name] = None

            vector.metadata = self._metadata_for_context(context, vector.metrics)
        except Exception as exc:
            vector = MetricsVector(layer=self.LAYER_NAME)
            logger.warning("[DECISION] failed to score file: %s", exc)
            vector.errors.append(f"decision metrics failed: {exc}")
            vector.metrics = self._safe_default_metrics()

        return LayerResult.from_vector(vector)

    def summarize(self, decision_result: LayerResult) -> LayerResult:
        return LayerResult.from_vector(self._build_summary_vector(decision_result))

    # -- Metric handlers ---------------------------------------------------

    def refactor_score(self, context: DecisionAnalysisContext) -> float:
        logger.debug("[DECISION] computing final refactor score")
        components = {
            "complexity_score": self.complexity_score(context),
            "history_score": self.history_score(context),
            "duplication_score": self.duplication_score(context),
            "architecture_score": self.architecture_score(context),
        }
        return self._round_score(self._weighted_score(components, self.component_weights))

    def complexity_score(self, context: DecisionAnalysisContext) -> float:
        metric_name = "complexity_score"
        if metric_name in context.component_cache:
            return context.component_cache[metric_name]

        logger.debug("[DECISION] computing complexity score")
        loc = self._loc(context)
        scores = {
            "max_cyclomatic_complexity": self._saturate(self._number(context, "max_cyclomatic_complexity"), 15.0),
            "max_cognitive_complexity": self._saturate(self._number(context, "max_cognitive_complexity"), 25.0),
            "average_cyclomatic_complexity": self._saturate(self._number(context, "average_cyclomatic_complexity"), 8.0),
            "average_cognitive_complexity": self._saturate(self._number(context, "average_cognitive_complexity"), 12.0),
            "size": self._saturate(loc, 500.0),
            "long_conditions_count": self._saturate(
                self._count_per_reference_loc(self._number(context, "long_conditions_count"), loc),
                5.0,
            ),
            "max_if_else_chain_length": self._saturate(max(0.0, self._number(context, "max_if_else_chain_length") - 1.0), 5.0),
            "average_parameters_count": self._saturate(max(0.0, self._number(context, "average_parameters_count") - 3.0), 4.0),
            "count_of_fixme_comments": self._saturate(
                self._count_per_reference_loc(self._number(context, "count_of_fixme_comments"), loc),
                5.0,
            ),
            "count_of_empty_except_blocks": self._saturate(
                self._count_per_reference_loc(self._number(context, "count_of_empty_except_blocks"), loc),
                3.0,
            ),
            "testing_coverage_gap": self._coverage_gap(context),
        }
        score = self._round_score(self._weighted_score(scores, self.complexity_metric_weights))
        context.component_cache[metric_name] = score
        return score

    def history_score(self, context: DecisionAnalysisContext) -> float:
        metric_name = "history_score"
        if metric_name in context.component_cache:
            return context.component_cache[metric_name]

        logger.debug("[DECISION] computing history score")
        scores = {
            "churn_to_size_ratio": self._saturate(self._number(context, "churn_to_size_ratio"), 8.0),
            "recent_update_count": self._saturate(self._number(context, "recent_update_count"), 12.0),
            "bug_fix_ratio": self._saturate(self._number(context, "bug_fix_ratio"), 0.5),
            "cyclomatic_complexity_growth_rate": self._saturate(max(0.0, self._number(context, "cyclomatic_complexity_growth_rate")), 5.0),
            "bug_fix_commit_count": self._saturate(self._number(context, "bug_fix_commit_count"), 6.0),
            "co_change_file_count": self._saturate(self._number(context, "co_change_file_count"), 12.0),
            "contributors_count": self._saturate(max(0.0, self._number(context, "contributors_count") - 1.0), 5.0),
            "recent_to_lifetime_update_ratio": self._clamp(self._number(context, "recent_to_lifetime_update_ratio")),
        }
        score = self._round_score(self._weighted_score(scores, self.history_metric_weights))
        context.component_cache[metric_name] = score
        return score

    def duplication_score(self, context: DecisionAnalysisContext) -> float:
        metric_name = "duplication_score"
        if metric_name in context.component_cache:
            return context.component_cache[metric_name]

        logger.debug("[DECISION] computing duplication score")
        loc = max(1.0, self._loc(context))
        max_similarity = self._number(context, "max_similarity_score")
        scores = {
            "duplicate_loc_ratio": self._clamp(self._number(context, "duplicate_loc_count") / loc),
            "duplicate_blocks_count": self._saturate(
                self._count_per_reference_loc(self._number(context, "duplicate_blocks_count"), loc),
                6.0,
            ),
            "semantic_duplicate_blocks_count": self._saturate(
                self._count_per_reference_loc(self._number(context, "semantic_duplicate_blocks_count"), loc),
                4.0,
            ),
            "duplication_group_size": self._saturate(max(0.0, self._number(context, "duplication_group_size") - 1.0), 4.0),
            "duplicate_file_candidates_count": self._saturate(
                self._count_per_reference_loc(self._number(context, "duplicate_file_candidates_count"), loc),
                5.0,
            ),
            "max_similarity_score": self._saturate(max(0.0, max_similarity - 0.75), 0.25),
        }
        score = self._round_score(self._weighted_score(scores, self.duplication_metric_weights))
        context.component_cache[metric_name] = score
        return score

    def architecture_score(self, context: DecisionAnalysisContext) -> float:
        metric_name = "architecture_score"
        if metric_name in context.component_cache:
            return context.component_cache[metric_name]

        logger.debug("[DECISION] computing architecture score")
        fan_in = self._number(context, "fan_in")
        fan_out = self._number(context, "fan_out")
        scores = {
            "circular_dependency_size": self._saturate(max(0.0, self._number(context, "circular_dependency_size") - 1.0), 5.0),
            "betweenness_centrality": self._clamp(self._number(context, "betweenness_centrality")),
            "transitive_dependents_count": self._saturate(self._number(context, "transitive_dependents_count"), 30.0),
            "fan_out": self._saturate(fan_out, 15.0),
            "fan_in": self._saturate(fan_in, 15.0),
            "instability_index": self._clamp(self._number(context, "instability_index")),
        }
        score = self._round_score(self._weighted_score(scores, self.architecture_metric_weights))
        context.component_cache[metric_name] = score
        return score

    def score_confidence(self, context: DecisionAnalysisContext) -> float:
        logger.debug("[DECISION] computing score confidence")
        layer_coverage = len(context.available_layers & self.EXPECTED_INPUT_LAYERS) / len(self.EXPECTED_INPUT_LAYERS)
        metric_total = max(1, len(context.metrics))
        none_metric_penalty = min(0.30, context.none_metric_count / metric_total)
        error_penalty = min(0.50, context.error_count * 0.10)
        return self._round_score(layer_coverage * (1.0 - none_metric_penalty) * (1.0 - error_penalty))

    # -- Context and summary helpers --------------------------------------

    def _paths_for(self, result: LayerResult) -> tuple[Path, str]:
        relative_paths = {
            vector.relative_path
            for vector in result.vectors
            if vector.relative_path is not None and vector.layer != self.LAYER_NAME
        }
        if len(relative_paths) != 1:
            raise ValueError("DecisionAnalysisLayer.run expects vectors for exactly one file")

        absolute_paths = {
            vector.absolute_path
            for vector in result.vectors
            if vector.absolute_path is not None and vector.layer != self.LAYER_NAME
        }
        if len(absolute_paths) != 1:
            raise ValueError("DecisionAnalysisLayer.run received inconsistent absolute paths")

        return next(iter(absolute_paths)), next(iter(relative_paths))

    def _build_context(
        self,
        absolute_path: Path,
        relative_path: str,
        result: LayerResult,
    ) -> DecisionAnalysisContext:
        metrics: dict[str, MetricValue] = {}
        available_layers: set[str] = set()
        error_count = 0
        none_metric_count = 0

        for vector in result.vectors:
            available_layers.add(vector.layer)
            error_count += len(vector.errors)
            for metric_name, metric_value in vector.metrics.items():
                metrics[metric_name] = metric_value
                if metric_value is None:
                    none_metric_count += 1

        return DecisionAnalysisContext(
            absolute_path=absolute_path,
            relative_path=relative_path,
            result=result,
            metrics=metrics,
            available_layers=available_layers,
            error_count=error_count,
            none_metric_count=none_metric_count,
        )

    def _metadata_for_context(
        self,
        context: DecisionAnalysisContext,
        computed_metrics: dict[str, MetricValue],
    ) -> dict[str, object]:
        component_scores = {
            key: float(computed_metrics.get(key) or 0.0)
            for key in self.component_weights
        }
        top_components = sorted(component_scores.items(), key=lambda item: item[1], reverse=True)
        refactor_score = float(computed_metrics.get("refactor_score") or 0.0)
        return {
            "scoring_model_version": self.SCORING_MODEL_VERSION,
            "count_density_reference_loc": self.COUNT_DENSITY_REFERENCE_LOC,
            "available_layers": sorted(context.available_layers),
            "component_weights": self.component_weights,
            "metric_weight_groups": {
                "complexity": self.complexity_metric_weights,
                "history": self.history_metric_weights,
                "duplication": self.duplication_metric_weights,
                "architecture": self.architecture_metric_weights,
            },
            "priority_band": self._priority_band(refactor_score),
            "top_contributing_components": [
                {"component": component, "score": round(score, 6)}
                for component, score in top_components
                if score > 0.0
            ],
            "upstream_error_count": context.error_count,
            "none_metric_count": context.none_metric_count,
        }

    def _build_summary_vector(self, decision_result: LayerResult) -> MetricsVector:
        vector = MetricsVector(layer=self.LAYER_NAME)
        scored_files = [
            (str(file_vector.relative_path), float(file_vector.metrics.get("refactor_score") or 0.0))
            for file_vector in decision_result.vectors
            if file_vector.relative_path is not None
        ]
        scores = [score for _, score in scored_files]
        top_files = sorted(scored_files, key=lambda item: item[1], reverse=True)[:10]

        vector.metrics = {
            "files_scored_count": len(scored_files),
            "average_refactor_score": self._round_score(sum(scores) / len(scores) if scores else 0.0),
            "max_refactor_score": self._round_score(max(scores, default=0.0)),
            "high_priority_files_count": sum(
                1 for score in scores if score >= self.HIGH_PRIORITY_THRESHOLD
            ),
            "medium_priority_files_count": sum(
                1
                for score in scores
                if self.MEDIUM_PRIORITY_THRESHOLD <= score < self.HIGH_PRIORITY_THRESHOLD
            ),
        }
        vector.metadata = {
            "scoring_model_version": self.SCORING_MODEL_VERSION,
            "count_density_reference_loc": self.COUNT_DENSITY_REFERENCE_LOC,
            "top_refactor_candidates": [
                {"file_path": file_path, "refactor_score": self._round_score(score)}
                for file_path, score in top_files
            ],
            "score_range": {"min": 0.0, "max": 1.0},
            "priority_thresholds": {
                "high": self.HIGH_PRIORITY_THRESHOLD,
                "medium": self.MEDIUM_PRIORITY_THRESHOLD,
            },
        }
        return vector

    # -- Numeric helpers ---------------------------------------------------

    def _number(self, context: DecisionAnalysisContext, metric_name: str, default: float = 0.0) -> float:
        value = context.metrics.get(metric_name)
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default

        if math.isnan(number) or math.isinf(number):
            return default
        return number

    def _loc(self, context: DecisionAnalysisContext) -> float:
        return max(
            self._number(context, "logical_lines_of_code"),
            self._number(context, "lines_of_code"),
            1.0,
        )

    def _coverage_gap(self, context: DecisionAnalysisContext) -> float:
        if "testing_coverage" not in context.metrics:
            return 0.0
        return 1.0 - self._clamp(self._number(context, "testing_coverage") / 100.0)

    def _weighted_score(self, scores: dict[str, float], weights: dict[str, float]) -> float:
        score_names = set(scores)
        weight_names = set(weights)
        if score_names != weight_names:
            missing_scores = sorted(weight_names - score_names)
            unexpected_scores = sorted(score_names - weight_names)
            raise ValueError(
                "Score and weight keys must match "
                f"(missing scores: {missing_scores}; unexpected scores: {unexpected_scores})"
            )

        invalid_weights = sorted(
            name
            for name, weight in weights.items()
            if not math.isfinite(weight) or weight < 0.0
        )
        if invalid_weights:
            raise ValueError(f"Weights must be finite and non-negative: {invalid_weights}")

        weight_total = math.fsum(weights.values())
        if not math.isclose(weight_total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(f"Weights must sum to 1.0; got {weight_total}")

        return self._clamp(math.fsum(scores[name] * weights[name] for name in weights))

    def _count_per_reference_loc(self, count: float, loc: float) -> float:
        return max(0.0, count) * self.COUNT_DENSITY_REFERENCE_LOC / max(1.0, loc)

    def _saturate(self, value: float, saturation: float) -> float:
        if saturation <= 0:
            return 0.0
        return self._clamp(value / saturation)

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _round_score(self, value: float) -> float:
        return round(self._clamp(value), 6)

    def _priority_band(self, score: float) -> str:
        if score >= self.HIGH_PRIORITY_THRESHOLD:
            return "high"
        if score >= self.MEDIUM_PRIORITY_THRESHOLD:
            return "medium"
        return "low"

    def _safe_default_metrics(self) -> dict[str, int | float]:
        return {
            "refactor_score": 0.0,
            "complexity_score": 0.0,
            "history_score": 0.0,
            "duplication_score": 0.0,
            "architecture_score": 0.0,
            "score_confidence": 0.0,
        }
