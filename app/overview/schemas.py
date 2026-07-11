from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
