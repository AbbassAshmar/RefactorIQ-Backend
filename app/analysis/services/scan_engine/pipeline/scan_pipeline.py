# app/scans/pipeline/scan_pipeline.py

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import UUID

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector
from app.analysis.services.scan_engine.pipeline.layers.static_analysis_layer import StaticAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.history_analysis_layer import HistoryAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.duplication_analysis_layer import DuplicationAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.architecture_analysis_layer import ArchitectureAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.decision_analysis_layer import DecisionAnalysisLayer

logger = logging.getLogger(__name__)


class ScanPipeline:

    def __init__(self, scan_id: UUID, file_paths: list[str]):
        self.scan_id = scan_id
        self.file_paths = file_paths

        # Instantiate layers — inject dependencies here as they grow
        self.static_layer = StaticAnalysisLayer()
        self.history_layer = HistoryAnalysisLayer()
        self.duplication_layer = DuplicationAnalysisLayer()
        self.architectural_layer = ArchitectureAnalysisLayer()
        self.decision_layer = DecisionAnalysisLayer()

    def run(self) -> list[MetricsVector]:
        all_vectors: list[MetricsVector] = []

        # ── Stage 1: per-file layers, run in parallel ─────────────────────
        logger.info("[PIPELINE] stage 1 — per-file analysis (%d files)", len(self.file_paths))
        all_vectors.extend(self._run_per_file_stage())

        # ── Stage 2: cross-file layers, need all files ────────────────────
        logger.info("[PIPELINE] stage 2 — cross-file analysis")
        all_vectors.extend(self.duplication_layer.run(self.file_paths))
        all_vectors.extend(self.architectural_layer.run(self.file_paths))

        # ── Stage 3: aggregation ──────────────────────────────────────────
        logger.info("[PIPELINE] stage 3 — decision layer")
        all_vectors.append(self.decision_layer.run(all_vectors))

        return all_vectors

    def _run_per_file_stage(self) -> list[MetricsVector]:
        vectors = []
        # Each file runs both layer 1 and layer 2 concurrently
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self._run_file_layers, fp): fp
                for fp in self.file_paths
            }
            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    vectors.extend(future.result())
                except Exception as exc:
                    logger.error("[PIPELINE] file failed entirely: %s — %s", file_path, exc)
        return vectors

    def _run_file_layers(self, file_path: str) -> list[MetricsVector]:
        return [
            self.static_layer.run(file_path),
            self.history_layer.run(file_path),
        ]