from __future__ import annotations

import os
import uuid
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from math import isfinite
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.analysis.services.scan_engine.pipeline.metrics_vector import (
    LayerResult,
    validate_relative_path,
)
from app.core.exceptions.repository_exceptions import DatabaseOperationException
from app.models import (
    CircularDependencyGroup,
    CircularDependencyMember,
    CoChangeEdge,
    DependencyEdge,
    ScanFile,
)


class ScanResultRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def clear_scan(self, scan_id: uuid.UUID) -> None:
        try:
            group_ids = self._db.execute(
                select(CircularDependencyGroup.id).where(CircularDependencyGroup.scan_id == scan_id)
            ).scalars().all()
            if group_ids:
                self._db.execute(
                    delete(CircularDependencyMember).where(
                        CircularDependencyMember.group_id.in_(group_ids)
                    )
                )

            self._db.execute(delete(CoChangeEdge).where(CoChangeEdge.scan_id == scan_id))
            self._db.execute(delete(DependencyEdge).where(DependencyEdge.scan_id == scan_id))
            self._db.execute(delete(CircularDependencyGroup).where(CircularDependencyGroup.scan_id == scan_id))
            self._db.execute(delete(ScanFile).where(ScanFile.scan_id == scan_id))
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to clear scan analysis records",
                details={"scan_id": str(scan_id)},
            ) from exc

    def store_results(
        self,
        scan_id: uuid.UUID,
        relative_paths: list[str],
        result: LayerResult,
    ) -> list[ScanFile]:
        architecture_metadata = self._architecture_metadata(result)
        file_payloads = self._file_payloads(
            relative_paths=relative_paths,
            result=result,
        )

        records = [
            ScanFile(
                scan_id=scan_id,
                file_path=file_path,
                refactor_score=payload.get("refactor_score"),
                priority_band=payload.get("priority_band"),
                metrics=self._json_safe(payload.get("metrics", {})),
                metadata_json=self._json_safe(payload.get("metadata", {})),
                errors=self._json_safe(payload.get("errors", {})),
            )
            for file_path, payload in sorted(file_payloads.items())
        ]

        try:
            self._db.add_all(records)
            self._db.flush()

            file_by_path = {record.file_path: record for record in records}

            self._store_dependency_edges(scan_id, architecture_metadata, file_by_path)
            self._store_circular_dependency_groups(scan_id, architecture_metadata, file_by_path)
            self._store_co_change_edges(scan_id, result, file_by_path)

            self._db.commit()
            return records
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException(
                "Failed to store scan analysis records",
                details={"scan_id": str(scan_id), "file_count": len(records)},
            ) from exc

    def _file_payloads(
        self,
        *,
        relative_paths: list[str],
        result: LayerResult,
    ) -> dict[str, dict[str, Any]]:
        payloads = {
            validate_relative_path(relative_path): self._empty_payload()
            for relative_path in relative_paths
        }

        for vector in result.vectors:
            if vector.relative_path is None:
                continue

            relative_path = validate_relative_path(vector.relative_path)
            payload = payloads.setdefault(relative_path, self._empty_payload())
            payload["metrics"][vector.layer] = self._json_safe(vector.metrics)
            payload["metadata"][vector.layer] = self._json_safe(vector.metadata)
            if vector.errors:
                payload["errors"][vector.layer] = self._json_safe(vector.errors)

            if vector.layer == "decision_analysis":
                score = vector.metrics.get("refactor_score")
                if score is not None:
                    payload["refactor_score"] = Decimal(str(round(float(score), 5)))
                priority_band = vector.metadata.get("priority_band")
                if priority_band is not None:
                    payload["priority_band"] = str(priority_band)

        return payloads

    def _empty_payload(self) -> dict[str, Any]:
        return {
            "metrics": {},
            "metadata": {},
            "errors": {},
            "refactor_score": None,
            "priority_band": None,
        }

    def _store_dependency_edges(
        self,
        scan_id: uuid.UUID,
        architecture_metadata: dict[str, Any],
        file_by_path: dict[str, ScanFile],
    ) -> None:
        edges = architecture_metadata.get("dependency_edges", [])
        records = []
        seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
        for edge in edges:
            if not isinstance(edge, (list, tuple)) or len(edge) != 2:
                continue
            source = file_by_path.get(str(edge[0]))
            target = file_by_path.get(str(edge[1]))
            if source is None or target is None or source.id == target.id:
                continue
            key = (source.id, target.id)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                DependencyEdge(
                    scan_id=scan_id,
                    source_file_id=source.id,
                    target_file_id=target.id,
                )
            )
        self._db.add_all(records)

    def _store_circular_dependency_groups(
        self,
        scan_id: uuid.UUID,
        architecture_metadata: dict[str, Any],
        file_by_path: dict[str, ScanFile],
    ) -> None:
        groups = architecture_metadata.get("circular_dependency_groups") or architecture_metadata.get("sccs", [])
        for group_metadata in groups:
            if not isinstance(group_metadata, dict):
                continue
            members = list(
                {
                    file_by_path[relative_path].id
                    for relative_path in group_metadata.get("nodes", [])
                    if isinstance(relative_path, str) and relative_path in file_by_path
                }
            )
            if len(members) <= 1:
                continue

            group = CircularDependencyGroup(scan_id=scan_id, size=len(members))
            self._db.add(group)
            self._db.flush()
            self._db.add_all(
                CircularDependencyMember(group_id=group.id, file_id=file_id)
                for file_id in sorted(set(members), key=str)
            )

    def _store_co_change_edges(
        self,
        scan_id: uuid.UUID,
        result: LayerResult,
        file_by_path: dict[str, ScanFile],
    ) -> None:
        records = []
        seen: set[tuple[str, str]] = set()
        for vector in result.vectors:
            if vector.layer != "history_analysis" or vector.relative_path is None:
                continue

            source = file_by_path.get(vector.relative_path)
            if source is None:
                continue

            for peer_path in vector.metadata.get("co_changed_files", []):
                target = file_by_path.get(str(peer_path))
                if target is None or target.id == source.id:
                    continue

                left, right = self._ordered_ids(source.id, target.id)
                key = (str(left), str(right))
                if key in seen:
                    continue
                seen.add(key)
                records.append(
                    CoChangeEdge(
                        scan_id=scan_id,
                        file_id_a=left,
                        file_id_b=right,
                    )
                )
        self._db.add_all(records)

    def _architecture_metadata(self, result: LayerResult) -> dict[str, Any]:
        if "dependency_edges" in result.metadata or "circular_dependency_groups" in result.metadata:
            return result.metadata
        return {}

    def _ordered_ids(self, left: uuid.UUID, right: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
        if str(left) < str(right):
            return left, right
        return right, left

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, float) and not isfinite(value):
            return None
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (Path, os.PathLike)):
            return str(value)
        if is_dataclass(value):
            return self._json_safe(asdict(value))
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        return value
