from __future__ import annotations

import json
import uuid
from collections import defaultdict
from typing import Any

from app.scan_visualization.repository import ScanVisualizationRepository
from app.scan_visualization.schemas import (
    ScanVisualizationCircularDependency,
    ScanVisualizationFile,
    ScanVisualizationRunSummary,
    ScanVisualizationSnapshot,
    ScanVisualizationVector,
)


class ScanVisualizationService:
    LAYER_ORDER = {
        "static_analysis": 0,
        "history_analysis": 1,
        "duplication_analysis": 2,
        "architecture_analysis": 3,
        "decision_analysis": 4,
    }

    def __init__(self, repository: ScanVisualizationRepository) -> None:
        self._repository = repository

    def list_runs(self, limit: int = 25) -> list[ScanVisualizationRunSummary]:
        return self._repository.list_runs(limit=limit)

    def latest_snapshot(self) -> ScanVisualizationSnapshot:
        scan_id = self._repository.latest_scan_id()
        if scan_id is None:
            return self._build_snapshot(scan_id=None, records=[])
        return self.snapshot(scan_id)

    def snapshot(self, scan_id: uuid.UUID) -> ScanVisualizationSnapshot:
        return self._build_snapshot(
            scan_id=scan_id,
            records=self._repository.list_by_scan_id(scan_id),
        )

    def _build_snapshot(
        self,
        scan_id: uuid.UUID | None,
        records: list[ScanVisualizationVector],
    ) -> ScanVisualizationSnapshot:
        files_by_path: dict[str, list[ScanVisualizationVector]] = defaultdict(list)
        codebase_layers: list[ScanVisualizationVector] = []

        for record in records:
            if record.file_path is None:
                codebase_layers.append(record)
            else:
                files_by_path[record.file_path].append(record)

        files = [
            ScanVisualizationFile(
                file_path=file_path,
                layers=sorted(layers, key=self._layer_sort_key),
            )
            for file_path, layers in sorted(files_by_path.items())
        ]

        return ScanVisualizationSnapshot(
            scan_id=scan_id,
            files=files,
            codebase_layers=sorted(codebase_layers, key=self._layer_sort_key),
            records=sorted(records, key=self._record_sort_key),
            circular_dependencies=self._circular_dependencies(records),
        )

    def _circular_dependencies(
        self,
        records: list[ScanVisualizationVector],
    ) -> list[ScanVisualizationCircularDependency]:
        seen: set[str] = set()
        dependencies: list[ScanVisualizationCircularDependency] = []

        for record in records:
            sccs = record.metadata.get("sccs")
            if not isinstance(sccs, list):
                continue

            for component in sccs:
                if not isinstance(component, dict):
                    continue

                nodes = self._string_list(component.get("nodes"))
                edges = self._edge_list(component.get("edges"))
                key = json.dumps(
                    {
                        "layer": record.layer,
                        "nodes": sorted(nodes),
                        "edges": sorted(edges),
                    },
                    sort_keys=True,
                )
                if not nodes or key in seen:
                    continue

                seen.add(key)
                dependencies.append(
                    ScanVisualizationCircularDependency(
                        layer=record.layer,
                        file_path=record.file_path,
                        nodes=nodes,
                        edges=edges,
                    )
                )

        return dependencies

    def _layer_sort_key(self, record: ScanVisualizationVector) -> tuple[int, str]:
        return (self.LAYER_ORDER.get(record.layer, 100), record.layer)

    def _record_sort_key(self, record: ScanVisualizationVector) -> tuple[str, int, str]:
        return (
            record.file_path or "",
            self.LAYER_ORDER.get(record.layer, 100),
            record.layer,
        )

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

    def _edge_list(self, value: Any) -> list[list[str]]:
        if not isinstance(value, list):
            return []

        edges: list[list[str]] = []
        for edge in value:
            if isinstance(edge, (list, tuple)) and len(edge) == 2:
                edges.append([str(edge[0]), str(edge[1])])
        return edges
