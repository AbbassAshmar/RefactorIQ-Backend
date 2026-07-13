from __future__ import annotations

import json
import uuid
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any

from app.core.exceptions.domain_exceptions import EntityNotFoundError, ExternalDependencyError, PersistenceError
from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.core.constants import (
    DIRECTORY_INSIGHT_PROMPT,
    PREVIOUS_TREND_SCAN_COUNT,
    PRIORITY_BANDS,
    RISKY_PRIORITY_BANDS,
    TOP_DIRECTORY_COUNT,
    TOP_REFACTOR_FILE_COUNT,
)
from app.overview.overview_dtos import (
    PriorityBandSummary,
    RiskByDirectoryItem,
    RiskByDirectoryResponse,
    DirectoryInsightResponse,
    RiskTrendPoint,
    RiskTrendResponse,
    ScanSummaryResponse,
    TopRefactorFile,
    TopRefactorFilesResponse,
)
from app.overview.overview_repository import OverviewRepository
from app.utils.llm_provider import LlmProvider


class OverviewService:
    def __init__(self, repository: OverviewRepository, summary_provider: LlmProvider | None = None) -> None:
        self._repository = repository
        self._summary_provider = summary_provider

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

    def directory_insight(self, user_id: uuid.UUID, scan_id: uuid.UUID) -> DirectoryInsightResponse:
        try:
            files = self._repository.list_files_for_directory_risk(user_id, scan_id)
            directories = self._directory_insight_context(files)
            if not directories:
                return DirectoryInsightResponse(
                    scan_id=scan_id,
                    title="Recommended focus area",
                    summary="No directory risk data is available for this scan.",
                    explanation="There are no scored directories to compare yet.",
                    recommendation="Run a successful scan before planning refactoring work.",
                    priority_directories=[],
                )

            if self._summary_provider is None:
                raise ExternalDependencyError("AI summary provider is not configured")

            context = json.dumps(
                {"scan_id": str(scan_id), "directories": directories},
                default=str,
                sort_keys=True,
            )
            raw_insight = self._summary_provider.generate(
                DIRECTORY_INSIGHT_PROMPT.format(context=context)
            )
            return self._parse_directory_insight(raw_insight, scan_id)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("successful scan", scan_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to build directory insight") from exc

    def _directory_insight_context(self, files: list[Any]) -> list[dict[str, Any]]:
        grouped: dict[str, list[Any]] = defaultdict(list)
        for file in files:
            grouped[self._directory_for(file.file_path)].append(file)

        summaries = []
        for directory, directory_files in grouped.items():
            scores = [self._percent_score(file.refactor_score) for file in directory_files]
            priority_counts = Counter((file.priority_band or "unknown").lower() for file in directory_files)
            reasons = Counter(
                reason
                for file in directory_files
                for reason in self._friendly_risk_reasons(file)
            )
            top_files = sorted(
                directory_files,
                key=lambda file: (-self._percent_score(file.refactor_score), file.file_path),
            )[:3]
            summaries.append(
                {
                    "path": directory,
                    "critical_files": priority_counts.get("critical", 0),
                    "high_files": priority_counts.get("high", 0),
                    "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
                    "top_risk_reasons": [reason for reason, _ in reasons.most_common(3)],
                    "top_files": [
                        {
                            "path": file.file_path,
                            "priority": (file.priority_band or "unknown").lower(),
                            "risk_score": self._percent_score(file.refactor_score),
                        }
                        for file in top_files
                    ],
                }
            )

        return sorted(
            summaries,
            key=lambda item: (
                -(item["critical_files"] + item["high_files"]),
                -item["average_score"],
                item["path"],
            ),
        )[:TOP_DIRECTORY_COUNT]

    def _friendly_risk_reasons(self, file: Any) -> list[str]:
        decision_metadata = file.metadata.get("decision_analysis", {})
        if not isinstance(decision_metadata, dict):
            return []

        labels = {
            "complexity_score": "maintenance complexity",
            "history_score": "frequent changes",
            "duplication_score": "repeated code",
            "architecture_score": "shared system impact",
        }
        return [
            labels[item.get("component")]
            for item in decision_metadata.get("top_contributing_components", [])
            if isinstance(item, dict) and item.get("component") in labels
        ][:2]

    def _parse_directory_insight(self, raw_insight: str, scan_id: uuid.UUID) -> DirectoryInsightResponse:
        text = raw_insight.strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()

        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ExternalDependencyError("AI returned an invalid directory insight")

        try:
            payload = json.loads(text[start:end + 1])
            return DirectoryInsightResponse.model_validate({"scan_id": scan_id, **payload})
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ExternalDependencyError("AI returned an invalid directory insight") from exc

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
