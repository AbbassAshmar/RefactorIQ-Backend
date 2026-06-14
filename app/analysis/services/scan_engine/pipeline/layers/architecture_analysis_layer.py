

import ast
import logging
from app.scans.services.scan_execution_service.pipeline.metrics_vector import MetricsVector

logger = logging.getLogger(__name__)


class ArchitectureAnalysisLayer():
    LAYER_NAME = "architecture_analysis"

    METRICS = [ ]

    def run(self, file_paths: list[str]) -> list[MetricsVector]:
        vector = MetricsVector(layer=self.LAYER_NAME, file_path=file_paths[0] if file_paths else None)

        try:
            source = self._read_file(file_paths[0])
            tree = ast.parse(source)
        except Exception as exc:
            vector.errors.append(f"Failed to parse file: {exc}")
            return vector   # return empty vector, don't crash the pipeline

        for metric_name in self.METRICS:
            try:
                fn = getattr(self, metric_name)
                result = fn(source, tree)
                vector.metrics[metric_name] = result
            except Exception as exc:
                # one metric failing must never kill the whole layer
                vector.errors.append(f"{metric_name} failed: {exc}")
                vector.metrics[metric_name] = None

        return vector

    # ── Metric functions ─────────────────────────────────────────────────────

    def compute_loc(self, source: str, tree: ast.AST) -> int:
        logger.debug("[ARCHITECTURE] computing LOC")
        # TODO: use radon
        return 0

    def compute_cyclomatic_complexity(self, source: str, tree: ast.AST) -> float:
        logger.debug("[ARCHITECTURE] computing cyclomatic complexity")
        # TODO: use radon
        return 0.0

    def compute_cognitive_complexity(self, source: str, tree: ast.AST) -> float:
        logger.debug("[ARCHITECTURE] computing cognitive complexity")
        # TODO: use complexipy
        return 0.0

    def compute_function_count(self, source: str, tree: ast.AST) -> int:
        logger.debug("[ARCHITECTURE] computing function count")
        # TODO: AST walk
        return 0

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _read_file(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()