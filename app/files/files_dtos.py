"""File API response and repository DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class FileListRow:
    id: uuid.UUID
    file_path: str
    priority_band: str | None


@dataclass(frozen=True)
class PriorityDistributionRow:
    scan_id: uuid.UUID
    finished_at: datetime
    counts: dict[str, int]


@dataclass(frozen=True)
class FilesAnalyzedRow:
    scan_id: uuid.UUID
    finished_at: datetime
    file_count: int


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


@dataclass(frozen=True)
class DependencyEdgeRow:
    source_file_id: uuid.UUID
    target_file_id: uuid.UUID


class FileListItem(BaseModel):
    id: uuid.UUID
    file_path: str
    priority_band: str | None


class FileListResponse(BaseModel):
    scan_id: uuid.UUID
    files: list[FileListItem]


class PriorityBandCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class ScanPriorityDistributionPoint(BaseModel):
    scan_id: uuid.UUID
    finished_at: datetime
    priority_counts: PriorityBandCounts


class PriorityDistributionTrendResponse(BaseModel):
    series: list[ScanPriorityDistributionPoint]


class FilesAnalyzedPoint(BaseModel):
    scan_id: uuid.UUID
    finished_at: datetime
    files_analyzed: int


class FilesAnalyzedTrendResponse(BaseModel):
    series: list[FilesAnalyzedPoint]


class FileReference(BaseModel):
    id: uuid.UUID
    file_path: str
    priority_band: str | None = None


class FileRelationship(FileReference):
    relationship: str
    direction: str | None = None
    metrics: dict[str, Any]


class CircularDependency(BaseModel):
    group_id: uuid.UUID
    size: int
    members: list[FileReference]


class DependencyEdgeReference(BaseModel):
    source_file_id: uuid.UUID
    target_file_id: uuid.UUID


class DependencyGraphResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: uuid.UUID
    nodes: list[FileReference]
    edges: list[DependencyEdgeReference]


class ScanCircularDependenciesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: uuid.UUID
    circular_dependencies: list[CircularDependency]


class DuplicateMatch(BaseModel):
    match_type: str
    kind: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    max_similarity: float | None = None
    matched_files: list[FileReference]


class FileSummaries(BaseModel):
    general: str | None = None
    architectural: str | None = None
    error: str | None = None


class FileDetailsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    scan_id: uuid.UUID
    file_path: str
    language: str
    refactor_score: float | None
    priority_band: str | None
    created_at: datetime | None
    last_scan_at: datetime | None
    metrics: dict[str, Any]
    metadata: dict[str, Any]
    errors: dict[str, Any]
    dependencies: list[FileRelationship]
    co_changed_files: list[FileRelationship]
    circular_dependencies: list[CircularDependency]
    duplicate_matches: list[DuplicateMatch]
    summaries: FileSummaries | None = None
