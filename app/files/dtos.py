from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FileListRow:
    id: uuid.UUID
    file_path: str
    priority_band: str | None


@dataclass(frozen=True)
class FileDetailRow:
    id: uuid.UUID
    scan_id: uuid.UUID
    file_path: str
    refactor_score: float | None
    priority_band: str | None
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    scan_finished_at: datetime | None = None


@dataclass(frozen=True)
class FileRelationshipRow:
    id: uuid.UUID
    file_path: str
    priority_band: str | None
    metrics: dict[str, Any] = field(default_factory=dict)
    relationship: str = "dependency"
    direction: str | None = None


@dataclass(frozen=True)
class CircularDependencyRow:
    group_id: uuid.UUID
    size: int
    members: list[FileListRow]
