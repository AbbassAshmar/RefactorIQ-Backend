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
    component_cache: dict[str, float | None] = field(default_factory=dict)
    component_coverage: dict[str, float] = field(default_factory=dict)


MetricHandler = Callable[[DecisionAnalysisContext], int | float | str | bool | None]


class DecisionAnalysisLayer:
    """Layer 5 - per-file refactor priority scoring."""

    LAYER_NAME = "decision_analysis"
    SCORING_MODEL_VERSION = 3
    COUNT_DENSITY_REFERENCE_LOC = 500.0
    SIZE_SATURATION_LOC = 300.0
    DUPLICATION_MATERIALITY_LOC = 30.0
    BETWEENNESS_CENTRALITY_SATURATION = 0.05
    CIRCULAR_DEPENDENCY_SATURATION = 2.0
    DOMINANT_SIGNAL_WEIGHT = 0.65
    MIN_COMPONENT_METRIC_COVERAGE = 0.50
    HIGH_PRIORITY_THRESHOLD = 0.55
    MEDIUM_PRIORITY_THRESHOLD = 0.31
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
        self.component_dominance_multipliers: dict[str, float] = {
            # Static and duplication findings are direct maintainability debt.
            # History and architecture are exposure signals, so they amplify
            # urgency without eclipsing severe code-local findings.
            "complexity_score": 1.00,
            "history_score": 0.70,
            "duplication_score": 0.90,
            "architecture_score": 0.80,
        }
        self.complexity_metric_weights: dict[str, float] = {
            "max_cyclomatic_complexity": 0.18,
            "max_cognitive_complexity": 0.18,
            "average_cyclomatic_complexity": 0.07,
            "average_cognitive_complexity": 0.07,
            "size": 0.18,
            "long_conditions_count": 0.07,
            "max_if_else_chain_length": 0.06,
            "average_parameters_count": 0.07,
            "count_of_fixme_comments": 0.06,
            "count_of_empty_except_blocks": 0.04,
            "testing_coverage_gap": 0.02,
        }
        self.history_metric_weights: dict[str, float] = {
            "churn_to_size_ratio": 0.25,
            "recent_change_count": 0.18,
            "bug_fix_ratio": 0.18,
            "cyclomatic_complexity_growth_rate": 0.12,
            "bug_fix_commit_count": 0.10,
            "co_change_file_count": 0.10,
            "contributors_count": 0.04,
            "recent_to_lifetime_change_ratio": 0.03,
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
            # Runtime cycles are deployment hazards. Type-only/design cycles
            # remain visible, but receive less urgency than executable cycles.
            "runtime_circular_dependency_size": 0.18,
            "circular_dependency_size": 0.05,
            "betweenness_centrality": 0.15,
            "transitive_dependents_count": 0.14,
            "fan_out": 0.30,
            "fan_in": 0.12,
            "instability_index": 0.06,
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
                try:
                    vector.metrics[metric_name] = handler(context)
                except Exception as exc:
                    vector.errors.append(f"{metric_name} failed: {exc}")
                    vector.metrics[metric_name] = None
                    if metric_name in self.component_weights:
                        context.component_cache[metric_name] = None
                        context.component_coverage[metric_name] = 0.0

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

    def refactor_score(self, context: DecisionAnalysisContext) -> float | None:
        logger.debug("[DECISION] computing final refactor score")
        components = {
            "complexity_score": self.complexity_score(context),
            "history_score": self.history_score(context),
            "duplication_score": self.duplication_score(context),
            "architecture_score": self.architecture_score(context),
        }
        score, _ = self._aggregate_component_scores(components)
        return None if score is None else self._round_score(score)

    def complexity_score(self, context: DecisionAnalysisContext) -> float | None:
        metric_name = "complexity_score"
        if metric_name in context.component_cache:
            return context.component_cache[metric_name]

        logger.debug("[DECISION] computing complexity score")
        physical_loc = self._physical_loc(context)
        code_loc = self._code_loc(context)
        scores = {
            "max_cyclomatic_complexity": self._saturate_optional(
                self._optional_number(context, "max_cyclomatic_complexity"),
                15.0,
            ),
            "max_cognitive_complexity": self._saturate_optional(
                self._optional_number(context, "max_cognitive_complexity"),
                25.0,
            ),
            "average_cyclomatic_complexity": self._saturate_optional(
                self._optional_number(context, "average_cyclomatic_complexity"),
                8.0,
            ),
            "average_cognitive_complexity": self._saturate_optional(
                self._optional_number(context, "average_cognitive_complexity"),
                12.0,
            ),
            "size": self._saturate_optional(physical_loc, self.SIZE_SATURATION_LOC),
            "long_conditions_count": self._density_score(
                self._optional_number(context, "long_conditions_count"),
                code_loc,
                5.0,
            ),
            "max_if_else_chain_length": self._offset_saturation_score(
                self._optional_number(context, "max_if_else_chain_length"),
                offset=1.0,
                saturation=5.0,
            ),
            "average_parameters_count": self._offset_saturation_score(
                self._optional_number(context, "average_parameters_count"),
                offset=3.0,
                saturation=4.0,
            ),
            "count_of_fixme_comments": self._density_score(
                self._optional_number(context, "count_of_fixme_comments"),
                code_loc,
                5.0,
            ),
            "count_of_empty_except_blocks": self._density_score(
                self._optional_number(context, "count_of_empty_except_blocks"),
                code_loc,
                3.0,
            ),
            "testing_coverage_gap": self._coverage_gap(context),
        }
        score = self._component_score(
            context,
            metric_name,
            scores,
            self.complexity_metric_weights,
        )
        context.component_cache[metric_name] = score
        return score

    def history_score(self, context: DecisionAnalysisContext) -> float | None:
        metric_name = "history_score"
        if metric_name in context.component_cache:
            return context.component_cache[metric_name]

        logger.debug("[DECISION] computing history score")
        update_count = self._optional_number(context, "update_count")
        recent_update_count = self._optional_number(context, "recent_update_count")
        modification_count = (
            max(0.0, update_count - 1.0)
            if update_count is not None
            else None
        )
        recent_change_count = (
            min(max(0.0, recent_update_count), modification_count)
            if recent_update_count is not None and modification_count is not None
            else None
        )
        recent_change_ratio = (
            recent_change_count / modification_count
            if recent_change_count is not None and modification_count
            else 0.0
            if modification_count == 0.0
            else None
        )
        bug_fix_ratio = self._optional_number(context, "bug_fix_ratio")
        bug_fix_reliability = (
            modification_count / (modification_count + 2.0)
            if modification_count is not None
            else None
        )
        supported_bug_fix_ratio = (
            bug_fix_ratio * bug_fix_reliability
            if bug_fix_ratio is not None and bug_fix_reliability is not None
            else None
        )
        scores = {
            "churn_to_size_ratio": self._saturate_optional(
                self._optional_number(context, "churn_to_size_ratio"),
                8.0,
            ),
            "recent_change_count": self._saturate_optional(recent_change_count, 12.0),
            "bug_fix_ratio": self._saturate_optional(supported_bug_fix_ratio, 0.5),
            "cyclomatic_complexity_growth_rate": self._positive_saturation_score(
                self._optional_number(context, "cyclomatic_complexity_growth_rate"),
                5.0,
            ),
            "bug_fix_commit_count": self._saturate_optional(
                self._optional_number(context, "bug_fix_commit_count"),
                6.0,
            ),
            "co_change_file_count": self._saturate_optional(
                self._optional_number(context, "co_change_file_count"),
                12.0,
            ),
            "contributors_count": self._offset_saturation_score(
                self._optional_number(context, "contributors_count"),
                offset=1.0,
                saturation=5.0,
            ),
            "recent_to_lifetime_change_ratio": (
                self._clamp(recent_change_ratio)
                if recent_change_ratio is not None
                else None
            ),
        }
        score = self._component_score(
            context,
            metric_name,
            scores,
            self.history_metric_weights,
        )
        context.component_cache[metric_name] = score
        return score

    def duplication_score(self, context: DecisionAnalysisContext) -> float | None:
        metric_name = "duplication_score"
        if metric_name in context.component_cache:
            return context.component_cache[metric_name]

        logger.debug("[DECISION] computing duplication score")
        code_loc = self._code_loc(context)
        duplicate_loc_count = self._optional_number(context, "duplicate_loc_count")
        duplicate_loc_ratio = (
            self._clamp(duplicate_loc_count / max(1.0, code_loc))
            if duplicate_loc_count is not None and code_loc is not None
            else None
        )
        duplicate_materiality = self._saturate_optional(
            duplicate_loc_count,
            self.DUPLICATION_MATERIALITY_LOC,
        )
        max_similarity = self._optional_number(context, "max_similarity_score")
        scores = {
            "duplicate_loc_ratio": (
                duplicate_loc_ratio * duplicate_materiality
                if duplicate_loc_ratio is not None and duplicate_materiality is not None
                else None
            ),
            "duplicate_blocks_count": self._saturate_optional(
                self._optional_number(context, "duplicate_blocks_count"),
                4.0,
            ),
            "semantic_duplicate_blocks_count": self._saturate_optional(
                self._optional_number(context, "semantic_duplicate_blocks_count"),
                3.0,
            ),
            "duplication_group_size": self._offset_saturation_score(
                self._optional_number(context, "duplication_group_size"),
                offset=1.0,
                saturation=4.0,
            ),
            "duplicate_file_candidates_count": self._saturate_optional(
                self._optional_number(context, "duplicate_file_candidates_count"),
                5.0,
            ),
            "max_similarity_score": self._offset_saturation_score(
                max_similarity,
                offset=0.75,
                saturation=0.25,
            ),
        }
        score = self._component_score(
            context,
            metric_name,
            scores,
            self.duplication_metric_weights,
        )
        context.component_cache[metric_name] = score
        return score

    def architecture_score(self, context: DecisionAnalysisContext) -> float | None:
        metric_name = "architecture_score"
        if metric_name in context.component_cache:
            return context.component_cache[metric_name]

        logger.debug("[DECISION] computing architecture score")
        fan_in = self._optional_number(context, "fan_in")
        fan_out = self._optional_number(context, "fan_out")
        scores = {
            "runtime_circular_dependency_size": self._offset_saturation_score(
                self._optional_number(context, "runtime_circular_dependency_size"),
                offset=1.0,
                saturation=self.CIRCULAR_DEPENDENCY_SATURATION,
            ),
            "circular_dependency_size": self._offset_saturation_score(
                self._optional_number(context, "circular_dependency_size"),
                offset=1.0,
                saturation=self.CIRCULAR_DEPENDENCY_SATURATION,
            ),
            "betweenness_centrality": self._saturate_optional(
                self._optional_number(context, "betweenness_centrality"),
                self.BETWEENNESS_CENTRALITY_SATURATION,
            ),
            "transitive_dependents_count": self._saturate_optional(
                self._optional_number(context, "transitive_dependents_count"),
                30.0,
            ),
            "fan_out": self._saturate_optional(fan_out, 15.0),
            "fan_in": self._saturate_optional(fan_in, 15.0),
            "instability_index": self._clamp_optional(
                self._optional_number(context, "instability_index")
            ),
        }
        score = self._component_score(
            context,
            metric_name,
            scores,
            self.architecture_metric_weights,
        )
        context.component_cache[metric_name] = score
        return score

    def score_confidence(self, context: DecisionAnalysisContext) -> float:
        logger.debug("[DECISION] computing score confidence")
        weighted_coverage = math.fsum(
            self.component_weights[component_name]
            * context.component_coverage.get(component_name, 0.0)
            for component_name in self.component_weights
        )
        return self._round_score(weighted_coverage)

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
            key: self._finite_number(computed_metrics.get(key))
            for key in self.component_weights
        }
        contributions = self._component_contributions(component_scores)
        top_components = sorted(
            (
                (component, score, contributions.get(component, 0.0))
                for component, score in component_scores.items()
                if score is not None
            ),
            key=lambda item: item[2],
            reverse=True,
        )
        refactor_score = self._finite_number(computed_metrics.get("refactor_score"))
        return {
            "scoring_model_version": self.SCORING_MODEL_VERSION,
            "count_density_reference_loc": self.COUNT_DENSITY_REFERENCE_LOC,
            "normalization_references": {
                "size_loc": self.SIZE_SATURATION_LOC,
                "duplication_materiality_loc": self.DUPLICATION_MATERIALITY_LOC,
                "betweenness_centrality": self.BETWEENNESS_CENTRALITY_SATURATION,
                "circular_dependency_size": self.CIRCULAR_DEPENDENCY_SATURATION,
            },
            "available_layers": sorted(context.available_layers),
            "component_weights": self.component_weights,
            "component_dominance_multipliers": self.component_dominance_multipliers,
            "dominant_signal_weight": self.DOMINANT_SIGNAL_WEIGHT,
            "component_metric_coverage": {
                component: round(context.component_coverage.get(component, 0.0), 6)
                for component in self.component_weights
            },
            "metric_weight_groups": {
                "complexity": self.complexity_metric_weights,
                "history": self.history_metric_weights,
                "duplication": self.duplication_metric_weights,
                "architecture": self.architecture_metric_weights,
            },
            "priority_band": self._priority_band(refactor_score),
            "top_contributing_components": [
                {
                    "component": component,
                    "score": round(score, 6),
                    "weighted_contribution": round(contribution, 6),
                }
                for component, score, contribution in top_components
                if contribution > 0.0
            ],
            "upstream_error_count": context.error_count,
            "none_metric_count": context.none_metric_count,
        }

    def _build_summary_vector(self, decision_result: LayerResult) -> MetricsVector:
        vector = MetricsVector(layer=self.LAYER_NAME)
        file_vectors = [
            file_vector
            for file_vector in decision_result.vectors
            if file_vector.relative_path is not None
        ]
        scored_files: list[tuple[str, float]] = []
        for file_vector in file_vectors:
            score = self._finite_number(file_vector.metrics.get("refactor_score"))
            if score is not None:
                scored_files.append((str(file_vector.relative_path), score))

        scores = [score for _, score in scored_files]
        top_files = sorted(scored_files, key=lambda item: item[1], reverse=True)[:10]

        vector.metrics = {
            "files_evaluated_count": len(file_vectors),
            "files_scored_count": len(scored_files),
            "unscored_files_count": len(file_vectors) - len(scored_files),
            "average_refactor_score": (
                self._round_score(sum(scores) / len(scores))
                if scores
                else None
            ),
            "max_refactor_score": self._round_score(max(scores)) if scores else None,
            "high_priority_files_count": sum(
                1 for score in scores if score >= self.HIGH_PRIORITY_THRESHOLD
            ),
            "medium_priority_files_count": sum(
                1
                for score in scores
                if self.MEDIUM_PRIORITY_THRESHOLD <= score < self.HIGH_PRIORITY_THRESHOLD
            ),
            "low_priority_files_count": sum(
                1 for score in scores if score < self.MEDIUM_PRIORITY_THRESHOLD
            ),
        }
        vector.metadata = {
            "scoring_model_version": self.SCORING_MODEL_VERSION,
            "count_density_reference_loc": self.COUNT_DENSITY_REFERENCE_LOC,
            "dominant_signal_weight": self.DOMINANT_SIGNAL_WEIGHT,
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

    def _component_score(
        self,
        context: DecisionAnalysisContext,
        component_name: str,
        scores: dict[str, float | None],
        weights: dict[str, float],
    ) -> float | None:
        score, coverage = self._weighted_available_score(scores, weights)
        context.component_coverage[component_name] = coverage
        if score is None or coverage < self.MIN_COMPONENT_METRIC_COVERAGE:
            return None
        return self._round_score(score)

    def _aggregate_component_scores(
        self,
        scores: dict[str, float | None],
    ) -> tuple[float | None, str | None]:
        base_score, _ = self._weighted_available_score(scores, self.component_weights)
        if base_score is None:
            return None, None

        valid_scores = {
            name: score
            for name, score in scores.items()
            if score is not None
        }
        dominant_component = max(
            valid_scores,
            key=lambda name: (
                self.component_dominance_multipliers[name]
                * max(0.0, valid_scores[name] - base_score)
            ),
        )
        dominant_excess = (
            self.component_dominance_multipliers[dominant_component]
            * max(0.0, valid_scores[dominant_component] - base_score)
        )
        score = base_score + self.DOMINANT_SIGNAL_WEIGHT * dominant_excess
        return self._clamp(score), dominant_component

    def _component_contributions(
        self,
        scores: dict[str, float | None],
    ) -> dict[str, float]:
        valid_names = [name for name in self.component_weights if scores.get(name) is not None]
        if not valid_names:
            return {}

        available_weight = math.fsum(self.component_weights[name] for name in valid_names)
        contributions = {
            name: (
                self.component_weights[name]
                / available_weight
                * float(scores[name])
            )
            for name in valid_names
        }
        base_score = math.fsum(contributions.values())
        dominant_component = max(
            valid_names,
            key=lambda name: (
                self.component_dominance_multipliers[name]
                * max(0.0, float(scores[name]) - base_score)
            ),
        )
        contributions[dominant_component] += (
            self.DOMINANT_SIGNAL_WEIGHT
            * self.component_dominance_multipliers[dominant_component]
            * max(0.0, float(scores[dominant_component]) - base_score)
        )

        contribution_total = math.fsum(contributions.values())
        clamped_total = self._clamp(contribution_total)
        if contribution_total > 0.0 and contribution_total != clamped_total:
            scale = clamped_total / contribution_total
            contributions = {
                name: contribution * scale
                for name, contribution in contributions.items()
            }
        return contributions

    def _optional_number(
        self,
        context: DecisionAnalysisContext,
        metric_name: str,
    ) -> float | None:
        return self._finite_number(context.metrics.get(metric_name))

    def _finite_number(self, value: MetricValue) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if math.isnan(number) or math.isinf(number):
            return None
        return number

    def _physical_loc(self, context: DecisionAnalysisContext) -> float | None:
        values = [
            self._optional_number(context, metric_name)
            for metric_name in (
                "lines_of_code",
                "source_lines_of_code",
                "logical_lines_of_code",
            )
        ]
        available_values = [value for value in values if value is not None]
        return max(available_values) if available_values else None

    def _code_loc(self, context: DecisionAnalysisContext) -> float | None:
        for metric_name in (
            "source_lines_of_code",
            "logical_lines_of_code",
            "lines_of_code",
        ):
            value = self._optional_number(context, metric_name)
            if value is not None:
                return value
        return None

    def _coverage_gap(self, context: DecisionAnalysisContext) -> float | None:
        coverage = self._optional_number(context, "testing_coverage")
        if coverage is None:
            return None
        return 1.0 - self._clamp(coverage / 100.0)

    def _weighted_available_score(
        self,
        scores: dict[str, float | None],
        weights: dict[str, float],
    ) -> tuple[float | None, float]:
        self._validate_weight_configuration(scores, weights)
        valid_scores = {
            name: float(score)
            for name, score in scores.items()
            if score is not None
        }
        coverage = math.fsum(weights[name] for name in valid_scores)
        if not valid_scores or coverage <= 0.0:
            return None, 0.0

        if math.isclose(coverage, 1.0, rel_tol=0.0, abs_tol=1e-9):
            return self._weighted_score(valid_scores, weights), 1.0

        normalized_weights = {
            name: weights[name] / coverage
            for name in valid_scores
        }
        return self._weighted_score(valid_scores, normalized_weights), coverage

    def _weighted_score(self, scores: dict[str, float], weights: dict[str, float]) -> float:
        self._validate_weight_configuration(scores, weights)
        return self._clamp(math.fsum(scores[name] * weights[name] for name in weights))

    def _validate_weight_configuration(
        self,
        scores: dict[str, float | None],
        weights: dict[str, float],
    ) -> None:
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

    def _count_per_reference_loc(self, count: float, loc: float) -> float:
        return max(0.0, count) * self.COUNT_DENSITY_REFERENCE_LOC / max(1.0, loc)

    def _density_score(
        self,
        count: float | None,
        loc: float | None,
        saturation: float,
    ) -> float | None:
        if count is None or loc is None:
            return None
        return self._saturate(self._count_per_reference_loc(count, loc), saturation)

    def _saturate_optional(
        self,
        value: float | None,
        saturation: float,
    ) -> float | None:
        if value is None:
            return None
        return self._saturate(value, saturation)

    def _positive_saturation_score(
        self,
        value: float | None,
        saturation: float,
    ) -> float | None:
        if value is None:
            return None
        return self._saturate(max(0.0, value), saturation)

    def _offset_saturation_score(
        self,
        value: float | None,
        *,
        offset: float,
        saturation: float,
    ) -> float | None:
        if value is None:
            return None
        return self._saturate(max(0.0, value - offset), saturation)

    def _saturate(self, value: float, saturation: float) -> float:
        if saturation <= 0:
            return 0.0
        return self._clamp(value / saturation)

    def _clamp_optional(self, value: float | None) -> float | None:
        return None if value is None else self._clamp(value)

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _round_score(self, value: float) -> float:
        return round(self._clamp(value), 6)

    def _priority_band(self, score: float | None) -> str | None:
        if score is None:
            return None
        if score >= self.HIGH_PRIORITY_THRESHOLD:
            return "high"
        if score >= self.MEDIUM_PRIORITY_THRESHOLD:
            return "medium"
        return "low"

    def _safe_default_metrics(self) -> dict[str, int | float | None]:
        return {
            "refactor_score": None,
            "complexity_score": None,
            "history_score": None,
            "duplication_score": None,
            "architecture_score": None,
            "score_confidence": 0.0,
        }
