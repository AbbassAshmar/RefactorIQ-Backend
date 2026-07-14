"""Internal DTOs and explanation types for the AI explanation module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum


class AiExplanationType(str, Enum):
    SUMMARY = "summary"
    ARCHITECTURE_SUMMARY = "architecture_summary"
    DIRECTORIES_INSIGHT = "directories_insight"


@dataclass(frozen=True)
class AiExplanationRow:
    id: uuid.UUID
    type: str
    explanation: str
    file_id: uuid.UUID | None = None
    scan_id: uuid.UUID | None = None
