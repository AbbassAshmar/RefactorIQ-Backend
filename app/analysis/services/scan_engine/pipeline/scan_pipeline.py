# app/scans/pipeline/scan_pipeline.py

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.analysis.services.scan_engine.pipeline.metrics_vector import (
    LayerResult,
    MetricsVector,
    validate_relative_path,
)
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


class ScanAnalysisStorage(Protocol):
    def clear_scan(self, scan_id: UUID) -> None:
        ...

    def store_results(
        self,
        scan_id: UUID,
        relative_paths: list[str],
        result: LayerResult,
    ) -> object:
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
            analysis_storage: ScanAnalysisStorage | None = None,
        ):
        self.static_layer = static_layer
        self.history_layer = history_layer
        self.duplication_layer = duplication_layer
        self.architectural_layer = architectural_layer
        self.decision_layer = decision_layer
        self.visualization_storage = visualization_storage
        self.analysis_storage = analysis_storage

    def run(
        self,
        file_paths: list[str | Path],
        *,
        repo_root: str | Path,
        scan_id: UUID | None = None,
    ) -> LayerResult:
        file_vectors = self._prepare_file_vectors(file_paths, repo_root)
        scan_result = LayerResult()
        self._clear_visualization(scan_id)
        self._clear_analysis(scan_id)

        # ── Stage 1: per-file layers, run in parallel ─────────────────────
        logger.info("[PIPELINE] stage 1 — per-file analysis (%d files)", len(file_vectors))
        per_file_result = self._run_per_file_stage(file_vectors)
        self._record_visualization(scan_id, per_file_result)
        scan_result = self._merge_results([scan_result, per_file_result])

        # ── Stage 2: cross-file layers, need all files ────────────────────
        logger.info("[PIPELINE] stage 2 — cross-file analysis")
        duplication_result = self.duplication_layer.run(
            [vector.for_layer(self.duplication_layer.LAYER_NAME) for vector in file_vectors]
        )
        self._record_visualization(scan_id, duplication_result)
        scan_result = self._merge_results([scan_result, duplication_result])

        architecture_result = self.architectural_layer.run(
            [vector.for_layer(self.architectural_layer.LAYER_NAME) for vector in file_vectors]
        )
        self._record_visualization(scan_id, architecture_result)
        scan_result = self._merge_results([scan_result, architecture_result])

        # ── Stage 3: aggregation ──────────────────────────────────────────
        logger.info("[PIPELINE] stage 3 — decision layer")
        decision_result = self._run_decision_stage(scan_result)
        self._record_visualization(scan_id, decision_result)
        scan_result = self._merge_results([scan_result, decision_result])

        self._store_analysis_results(
            scan_id,
            [vector.relative_path for vector in file_vectors if vector.relative_path is not None],
            scan_result,
        )

        return scan_result

    def _prepare_file_vectors(
        self,
        file_paths: list[str | Path],
        repo_root: str | Path,
    ) -> list[MetricsVector]:
        root = Path(repo_root).resolve()
        vectors: list[MetricsVector] = []
        for raw_path in file_paths:
            absolute_path = Path(raw_path).resolve()
            try:
                relative_path = absolute_path.relative_to(root).as_posix()
            except ValueError as exc:
                raise ValueError(f"File is outside scan workspace: {absolute_path}") from exc
            vectors.append(
                MetricsVector(
                    layer=self.static_layer.LAYER_NAME,
                    absolute_path=absolute_path,
                    relative_path=validate_relative_path(relative_path),
                )
            )
        return vectors

    def _run_per_file_stage(self, file_vectors: list[MetricsVector]) -> LayerResult:
        results: list[LayerResult] = []
        # Each file runs both layer 1 and layer 2 concurrently
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self._run_file_layers, vector): vector
                for vector in file_vectors
            }
            for future in as_completed(futures):
                vector = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    logger.error("[PIPELINE] file failed entirely: %s — %s", vector.relative_path, exc)
        return self._merge_results(results)

    def _run_file_layers(self, vector: MetricsVector) -> LayerResult:
        return self._merge_results(
            [
                self.static_layer.run(vector),
                self.history_layer.run(vector.for_layer(self.history_layer.LAYER_NAME)),
            ]
        )

    def _run_decision_stage(self, result: LayerResult) -> LayerResult:
        grouped: dict[str, LayerResult] = defaultdict(LayerResult)
        for vector in result.vectors:
            if vector.relative_path is None:
                continue
            grouped[vector.relative_path].vectors.append(vector)

        decision_results = [
            self.decision_layer.run(file_result)
            for _, file_result in sorted(grouped.items())
        ]
        decision_result = self._merge_results(decision_results)
        summary_result = self.decision_layer.summarize(decision_result)
        return self._merge_results([decision_result, summary_result])

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

    def _clear_analysis(self, scan_id: UUID | None) -> None:
        if scan_id is None or self.analysis_storage is None:
            return

        try:
            self.analysis_storage.clear_scan(scan_id)
        except Exception:
            logger.warning(
                "[PIPELINE] failed to clear analysis records for scan %s",
                scan_id,
                exc_info=True,
            )

    def _record_visualization(self, scan_id: UUID | None, result: LayerResult) -> None:
        if scan_id is None or self.visualization_storage is None or not result.vectors:
            return

        for vector in result.vectors:
            vector.scan_id = scan_id

        try:
            self.visualization_storage.store_vectors(scan_id, result.vectors)
        except Exception:
            logger.warning(
                "[PIPELINE] failed to store %d visualization vectors for scan %s",
                len(result.vectors),
                scan_id,
                exc_info=True,
            )

    def _store_analysis_results(
        self,
        scan_id: UUID | None,
        relative_paths: list[str],
        result: LayerResult,
    ) -> None:
        if scan_id is None or self.analysis_storage is None:
            return

        for vector in result.vectors:
            vector.scan_id = scan_id

        try:
            self.analysis_storage.store_results(scan_id, relative_paths, result)
        except Exception:
            logger.warning(
                "[PIPELINE] failed to store analysis records for scan %s",
                scan_id,
                exc_info=True,
            )

    def _merge_results(self, results: list[LayerResult]) -> LayerResult:
        merged = LayerResult()
        for result in results:
            merged.vectors.extend(result.vectors)
            if len(result.vectors) == 1 and result.metadata is result.vectors[0].metadata:
                continue
            for key, value in result.metadata.items():
                if key not in merged.metadata:
                    merged.metadata[key] = value
                elif isinstance(merged.metadata[key], list) and isinstance(value, list):
                    merged.metadata[key].extend(value)
                elif isinstance(merged.metadata[key], dict) and isinstance(value, dict):
                    merged.metadata[key].update(value)
        return merged
