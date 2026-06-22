from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ScanVisualizationVector(BaseModel):
    id: uuid.UUID
    scan_id: uuid.UUID | None
    layer: str
    file_path: str | None
    metrics: dict[str, Any]
    errors: list[str]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScanVisualizationFile(BaseModel):
    file_path: str
    layers: list[ScanVisualizationVector]


class ScanVisualizationCircularDependency(BaseModel):
    layer: str
    file_path: str | None = None
    nodes: list[str]
    edges: list[list[str]] = []


class ScanVisualizationRunSummary(BaseModel):
    scan_id: uuid.UUID
    vector_count: int
    file_count: int
    captured_at: datetime


class ScanVisualizationSnapshot(BaseModel):
    scan_id: uuid.UUID | None
    files: list[ScanVisualizationFile]
    codebase_layers: list[ScanVisualizationVector]
    records: list[ScanVisualizationVector]
    circular_dependencies: list[ScanVisualizationCircularDependency]
