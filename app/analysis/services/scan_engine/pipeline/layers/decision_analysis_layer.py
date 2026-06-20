import logging
from collections import defaultdict

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector

logger = logging.getLogger(__name__)


class DecisionAnalysisLayer:
    """Layer 5 - deterministic scoring stub based on upstream metric vectors."""

    LAYER_NAME = "decision_analysis"

    def run(self, vectors: list[MetricsVector]) -> MetricsVector:
        vector = MetricsVector(layer=self.LAYER_NAME, file_path=None)

        try:
            grouped_vectors = self._group_by_file(vectors)
            file_scores = {
                file_path: self._score_file(file_vectors)
                for file_path, file_vectors in grouped_vectors.items()
                if file_path is not None
            }
            top_files = sorted(file_scores.items(), key=lambda item: item[1], reverse=True)[:10]
            average_score = sum(file_scores.values()) / len(file_scores) if file_scores else 0.0

            vector.metrics = {
                "files_scored_count": len(file_scores),
                "average_refactor_score": round(average_score, 3),
                "max_refactor_score": round(max(file_scores.values(), default=0.0), 3),
                "high_priority_files_count": sum(1 for score in file_scores.values() if score >= 70.0),
                "medium_priority_files_count": sum(1 for score in file_scores.values() if 40.0 <= score < 70.0),
            }
            vector.metadata = {
                "top_refactor_candidates": [
                    {"file_path": file_path, "refactor_score": round(score, 3)}
                    for file_path, score in top_files
                ],
            }
        except Exception as exc:
            logger.warning("[DECISION] dummy layer failed: %s", exc)
            vector.errors.append(f"decision dummy metrics failed: {exc}")

        return vector

    def _group_by_file(self, vectors: list[MetricsVector]) -> dict[str | None, list[MetricsVector]]:
        grouped: dict[str | None, list[MetricsVector]] = defaultdict(list)
        for vector in vectors:
            grouped[vector.file_path].append(vector)
        return grouped

    def _score_file(self, vectors: list[MetricsVector]) -> float:
        metrics = {}
        for vector in vectors:
            metrics.update(vector.metrics)

        complexity_pressure = min(
            35.0,
            float(metrics.get("max_cyclomatic_complexity") or 0) * 1.8
            + float(metrics.get("max_cognitive_complexity") or 0) * 1.3
            + float(metrics.get("long_conditions_count") or 0) * 1.5,
        )
        history_pressure = min(
            25.0,
            float(metrics.get("recent_update_count") or 0) * 1.2
            + float(metrics.get("bug_fix_commit_count") or 0) * 2.0
            + float(metrics.get("churn_to_size_ratio") or 0) * 0.8,
        )
        duplication_pressure = min(
            20.0,
            float(metrics.get("duplicate_blocks_count") or 0) * 1.5
            + float(metrics.get("semantic_duplicate_blocks_count") or 0) * 2.0
            + float(metrics.get("duplication_group_size") or 0),
        )
        architecture_pressure = min(
            20.0,
            float(metrics.get("fan_in") or 0) * 0.8
            + float(metrics.get("transitive_dependents_count") or 0) * 0.35
            + float(metrics.get("centrality_score") or 0) * 7.0,
        )

        return min(100.0, complexity_pressure + history_pressure + duplication_pressure + architecture_pressure)
