from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from app.core.exceptions.domain_exceptions import EntityNotFoundError, PersistenceError
from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.overview.constants import (
    PREVIOUS_TREND_SCAN_COUNT,
    PRIORITY_BANDS,
    RISKY_PRIORITY_BANDS,
    TOP_DIRECTORY_COUNT,
    TOP_REFACTOR_FILE_COUNT,
)
from app.overview.repository import OverviewRepository
from app.overview.schemas import (
    PriorityBandSummary,
    RiskByDirectoryItem,
    RiskByDirectoryResponse,
    RiskTrendPoint,
    RiskTrendResponse,
    ScanSummaryResponse,
    TopRefactorFile,
    TopRefactorFilesResponse,
)


class OverviewService:
    def __init__(self, repository: OverviewRepository) -> None:
        self._repository = repository

    def risk_trend(self, user_id: uuid.UUID, scan_id: uuid.UUID) -> RiskTrendResponse:
        try:
            rows = self._repository.list_risk_trend_scans(
                user_id,
                scan_id,
                previous_count=PREVIOUS_TREND_SCAN_COUNT,
            )
            return RiskTrendResponse(
                scan_id=scan_id,
                series=[
                    RiskTrendPoint(
                        scan_id=row.scan_id,
                        finished_at=row.finished_at,
                        average_score=self._percent_score(row.average_refactor_score),
                    )
                    for row in rows
                ],
            )
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("successful scan", scan_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to build risk trend") from exc

    def scan_summary(self, user_id: uuid.UUID, scan_id: uuid.UUID) -> ScanSummaryResponse:
        try:
            counts = self._repository.get_priority_band_counts(user_id, scan_id)
            summary = {
                band: PriorityBandSummary(count=counts.get(band, 0), label=band.capitalize())
                for band in PRIORITY_BANDS
            }
            return ScanSummaryResponse(
                scan_id=scan_id,
                total_files=sum(counts.values()),
                severity_summary=summary,
            )
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("successful scan", scan_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to build scan summary") from exc

    def top_refactor_files(self, user_id: uuid.UUID, scan_id: uuid.UUID) -> TopRefactorFilesResponse:
        try:
            files = self._repository.list_top_files(user_id, scan_id, TOP_REFACTOR_FILE_COUNT)
            return TopRefactorFilesResponse(
                scan_id=scan_id,
                files=[
                    TopRefactorFile(
                        id=file.id,
                        file_path=file.file_path,
                        risk_score=self._percent_score(file.refactor_score),
                        priority_band=file.priority_band,
                        metrics=file.metrics,
                        metadata=file.metadata,
                        errors=file.errors,
                        fan_in=self._architecture_metric(file.metrics, "fan_in"),
                        fan_out=self._architecture_metric(file.metrics, "fan_out"),
                    )
                    for file in files
                ],
            )
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("successful scan", scan_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list top refactor files") from exc

    def risk_by_directory(self, user_id: uuid.UUID, scan_id: uuid.UUID) -> RiskByDirectoryResponse:
        try:
            files = self._repository.list_files_for_directory_risk(user_id, scan_id)
            counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for file in files:
                directory = self._directory_for(file.file_path)
                band = (file.priority_band or "unknown").lower()
                counts[directory][band] += 1

            directories = sorted(
                (
                    RiskByDirectoryItem(
                        directory=directory,
                        risky_file_count=sum(
                            value for band, value in band_counts.items()
                            if band in RISKY_PRIORITY_BANDS
                        ),
                        priority_counts=dict(band_counts),
                    )
                    for directory, band_counts in counts.items()
                ),
                key=lambda item: (-item.risky_file_count, item.directory),
            )[:TOP_DIRECTORY_COUNT]
            return RiskByDirectoryResponse(scan_id=scan_id, directories=directories)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("successful scan", scan_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to build directory risk") from exc

    def _directory_for(self, file_path: str) -> str:
        parent = PurePosixPath(file_path).parent.as_posix()
        return parent if parent != "." else "(root)"

    def _architecture_metric(self, metrics: dict[str, Any], key: str) -> float:
        architecture = metrics.get("architecture_analysis", {})
        if not isinstance(architecture, dict):
            architecture = metrics
        try:
            return float(architecture.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _percent_score(self, score: float | None) -> float:
        return round(max(0.0, min(1.0, float(score or 0.0))) * 100, 2)
