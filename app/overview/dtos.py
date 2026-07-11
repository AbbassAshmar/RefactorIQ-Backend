from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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
