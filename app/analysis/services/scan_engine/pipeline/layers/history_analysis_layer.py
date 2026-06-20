import hashlib
import logging
import os
import random

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector

logger = logging.getLogger(__name__)


class HistoryAnalysisLayer:
    """Layer 2 - deterministic production-shaped git history stub."""

    LAYER_NAME = "history_analysis"

    def run(self, file_path: str | os.PathLike[str]) -> MetricsVector:
        vector = MetricsVector(layer=self.LAYER_NAME, file_path=file_path)

        try:
            rng = self._rng(file_path)
            lifetime_updates = rng.randint(2, 90)
            recent_updates = rng.randint(0, min(lifetime_updates, 18))
            total_churn = rng.randint(lifetime_updates * 3, lifetime_updates * 45)
            current_loc = max(1, self._current_loc(file_path))
            bug_fix_commits = rng.randint(0, max(1, lifetime_updates // 4))

            vector.metrics = {
                "contributors_count": rng.randint(1, 7),
                "update_count": lifetime_updates,
                "recent_update_count": recent_updates,
                "historical_update_count": lifetime_updates - recent_updates,
                "recent_to_lifetime_update_ratio": round(recent_updates / lifetime_updates, 3),
                "churn_rate": total_churn,
                "churn_to_size_ratio": round(total_churn / current_loc, 3),
                "bug_fix_commit_count": bug_fix_commits,
                "bug_fix_ratio": round(bug_fix_commits / lifetime_updates, 3),
                "cyclomatic_complexity_growth_rate": round(rng.uniform(-0.15, 1.85), 3),
                "co_change_file_count": rng.randint(0, 12),
            }
        except Exception as exc:
            logger.warning("[HISTORY] dummy layer failed for %s: %s", file_path, exc)
            vector.errors.append(f"history dummy metrics failed: {exc}")

        return vector

    def _current_loc(self, file_path: str | os.PathLike[str]) -> int:
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return sum(1 for _ in file)
        except OSError:
            return 1

    def _rng(self, seed_value: str | os.PathLike[str]) -> random.Random:
        digest = hashlib.sha256(str(seed_value).encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))
