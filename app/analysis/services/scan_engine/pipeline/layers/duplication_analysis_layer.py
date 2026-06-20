import hashlib
import logging
import os
import random

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector

logger = logging.getLogger(__name__)


class DuplicationAnalysisLayer:
    """Layer 3 - deterministic production-shaped duplication stub."""

    LAYER_NAME = "duplication_analysis"

    def run(self, file_paths: list[str | os.PathLike[str]]) -> list[MetricsVector]:
        return [self._build_vector(file_path, file_paths) for file_path in file_paths]

    def _build_vector(
        self,
        file_path: str | os.PathLike[str],
        all_file_paths: list[str | os.PathLike[str]],
    ) -> MetricsVector:
        vector = MetricsVector(layer=self.LAYER_NAME, file_path=file_path)

        try:
            rng = self._rng(file_path)
            duplicate_blocks = rng.randint(0, 8)
            semantic_blocks = rng.randint(0, 5)
            group_size = 0 if duplicate_blocks == 0 and semantic_blocks == 0 else rng.randint(2, min(7, max(2, len(all_file_paths))))

            vector.metrics = {
                "duplicate_blocks_count": duplicate_blocks,
                "duplicate_loc_count": duplicate_blocks * rng.randint(4, 28),
                "duplication_group_size": group_size,
                "semantic_duplicate_blocks_count": semantic_blocks,
                "ast_duplicate_blocks_count": rng.randint(0, max(1, duplicate_blocks)),
                "max_similarity_score": round(rng.uniform(0.45, 0.98), 3) if group_size else 0.0,
                "duplicate_file_candidates_count": max(0, group_size - 1),
            }
        except Exception as exc:
            logger.warning("[DUPLICATION] dummy layer failed for %s: %s", file_path, exc)
            vector.errors.append(f"duplication dummy metrics failed: {exc}")

        return vector

    def _rng(self, seed_value: str | os.PathLike[str]) -> random.Random:
        digest = hashlib.sha256(f"{self.LAYER_NAME}:{seed_value}".encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))
