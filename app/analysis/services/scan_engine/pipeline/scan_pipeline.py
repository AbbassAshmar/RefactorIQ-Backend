# app/scans/pipeline/scan_pipeline.py

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Protocol
from uuid import UUID

from app.analysis.services.scan_engine.pipeline.metrics_vector import MetricsVector
from app.analysis.services.scan_engine.pipeline.layers.static_analysis_layer import StaticAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.history_analysis_layer import HistoryAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.duplication_analysis_layer import DuplicationAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.architecture_analysis_layer import ArchitectureAnalysisLayer
from app.analysis.services.scan_engine.pipeline.layers.decision_analysis_layer import DecisionAnalysisLayer

logger = logging.getLogger(__name__)


class ScanVisualizationStorage(Protocol):
    def clear_scan(self, scan_id: UUID) -> None:
        ...

    def store_vectors(self, scan_id: UUID, vectors: list[MetricsVector]) -> object:
        ...


class ScanPipeline:
    def __init__(
            self, 
            static_layer: StaticAnalysisLayer = None,
            history_layer: HistoryAnalysisLayer = None,
            duplication_layer: DuplicationAnalysisLayer = None,
            architectural_layer: ArchitectureAnalysisLayer = None,
            decision_layer: DecisionAnalysisLayer = None,
            visualization_storage: ScanVisualizationStorage | None = None,
        ):
        self.static_layer = static_layer
        self.history_layer = history_layer
        self.duplication_layer = duplication_layer
        self.architectural_layer = architectural_layer
        self.decision_layer = decision_layer
        self.visualization_storage = visualization_storage

    def run(self, file_paths: list[str], scan_id: UUID | None = None) -> list[MetricsVector]:
        all_vectors: list[MetricsVector] = []
        self._clear_visualization(scan_id)

        # ── Stage 1: per-file layers, run in parallel ─────────────────────
        logger.info("[PIPELINE] stage 1 — per-file analysis (%d files)", len(file_paths))
        per_file_vectors = self._run_per_file_stage(file_paths)
        self._record_vectors(scan_id, per_file_vectors)
        all_vectors.extend(per_file_vectors)

        # ── Stage 2: cross-file layers, need all files ────────────────────
        logger.info("[PIPELINE] stage 2 — cross-file analysis")
        duplication_vectors = self.duplication_layer.run(file_paths)
        self._record_vectors(scan_id, duplication_vectors)
        all_vectors.extend(duplication_vectors)

        architecture_vectors = self.architectural_layer.run(file_paths)
        self._record_vectors(scan_id, architecture_vectors)
        all_vectors.extend(architecture_vectors)

        # ── Stage 3: aggregation ──────────────────────────────────────────
        logger.info("[PIPELINE] stage 3 — decision layer")
        decision_vector = self.decision_layer.run(all_vectors)
        self._record_vectors(scan_id, [decision_vector])
        all_vectors.append(decision_vector)

        return all_vectors

    def _run_per_file_stage(self, file_paths: list[str]) -> list[MetricsVector]:
        vectors = []
        # Each file runs both layer 1 and layer 2 concurrently
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self._run_file_layers, fp): fp
                for fp in file_paths
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

    def _clear_visualization(self, scan_id: UUID | None) -> None:
        if scan_id is None or self.visualization_storage is None:
            return

        try:
            self.visualization_storage.clear_scan(scan_id)
        except Exception:
            logger.warning(
                "[PIPELINE] failed to clear visualization records for scan %s",
                scan_id,
                exc_info=True,
            )

    def _record_vectors(self, scan_id: UUID | None, vectors: list[MetricsVector]) -> None:
        if scan_id is None or self.visualization_storage is None or not vectors:
            return

        for vector in vectors:
            vector.scan_id = scan_id

        try:
            self.visualization_storage.store_vectors(scan_id, vectors)
        except Exception:
            logger.warning(
                "[PIPELINE] failed to store %d visualization vectors for scan %s",
                len(vectors),
                scan_id,
                exc_info=True,
            )
