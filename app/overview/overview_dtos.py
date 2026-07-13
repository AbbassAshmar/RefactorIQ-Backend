"""Overview API response and repository DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class OverviewScanScoreRow:
    scan_id: uuid.UUID
    finished_at: datetime | None
    average_refactor_score: float


@dataclass(frozen=True)
class OverviewFileRow:
    id: uuid.UUID
    file_path: str
    refactor_score: float | None
    priority_band: str | None
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, Any] = field(default_factory=dict)


class RiskTrendPoint(BaseModel):
    scan_id: uuid.UUID
    finished_at: datetime | None
    average_score: float


class RiskTrendResponse(BaseModel):
    scan_id: uuid.UUID
    series: list[RiskTrendPoint]


class PriorityBandSummary(BaseModel):
    count: int
    label: str


class ScanSummaryResponse(BaseModel):
    scan_id: uuid.UUID
    total_files: int
    severity_summary: dict[str, PriorityBandSummary]


class TopRefactorFile(BaseModel):
    id: uuid.UUID
    file_path: str
    risk_score: float = Field(ge=0)
    priority_band: str | None
    metrics: dict[str, Any]
    metadata: dict[str, Any]
    errors: dict[str, Any]
    fan_in: float = 0
    fan_out: float = 0


class TopRefactorFilesResponse(BaseModel):
    scan_id: uuid.UUID
    files: list[TopRefactorFile]


class RiskByDirectoryItem(BaseModel):
    directory: str
    risky_file_count: int
    priority_counts: dict[str, int]


class RiskByDirectoryResponse(BaseModel):
    scan_id: uuid.UUID
    directories: list[RiskByDirectoryItem]


class DirectoryPriorityItem(BaseModel):
    path: str
    priority: str
    reason: str


class DirectoryInsightResponse(BaseModel):
    scan_id: uuid.UUID
    title: str
    summary: str
    explanation: str
    recommendation: str
    priority_directories: list[DirectoryPriorityItem]
