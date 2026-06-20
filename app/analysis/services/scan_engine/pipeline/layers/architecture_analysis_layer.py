import hashlib
import logging
import os
import random

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector

logger = logging.getLogger(__name__)


class ArchitectureAnalysisLayer:
    """Layer 4 - deterministic production-shaped dependency graph stub."""

    LAYER_NAME = "architecture_analysis"

    def run(self, file_paths: list[str | os.PathLike[str]]) -> list[MetricsVector]:
        return [self._build_vector(file_path, len(file_paths)) for file_path in file_paths]

    def _build_vector(self, file_path: str | os.PathLike[str], total_files: int) -> MetricsVector:
        vector = MetricsVector(layer=self.LAYER_NAME, file_path=file_path)

        try:
            rng = self._rng(file_path)
            max_neighbors = max(1, min(total_files - 1, 20))
            fan_in = rng.randint(0, max_neighbors)
            fan_out = rng.randint(0, max_neighbors)
            dependency_total = fan_in + fan_out

            vector.metrics = {
                "fan_in": fan_in,
                "fan_out": fan_out,
                "transitive_dependents_count": rng.randint(fan_in, max(fan_in, min(total_files, fan_in * 5 + 3))),
                "dependency_depth": rng.randint(0, 8),
                "centrality_score": round(rng.uniform(0.0, 1.0), 3),
                "betweenness_centrality": round(rng.uniform(0.0, 0.65), 3),
                "circular_dependencies_count": rng.randint(0, 3),
                "instability_index": round(fan_out / dependency_total, 3) if dependency_total else 0.0,
            }
        except Exception as exc:
            logger.warning("[ARCHITECTURE] dummy layer failed for %s: %s", file_path, exc)
            vector.errors.append(f"architecture dummy metrics failed: {exc}")

        return vector

    def _rng(self, seed_value: str | os.PathLike[str]) -> random.Random:
        digest = hashlib.sha256(f"{self.LAYER_NAME}:{seed_value}".encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))
