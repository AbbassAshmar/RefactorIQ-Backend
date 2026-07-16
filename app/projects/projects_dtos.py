"""Project request, response, and internal deletion DTOs."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.enums import ScanStatus


class ProjectCreate(BaseModel):
    name: str
    repo_owner: str
    repo_name: str
    branch: str


class ProjectResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    repo_owner: str
    repo_name: str
    branch: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(ProjectResponse):
    """Project response with status derived from the project's scans."""

    status: ScanStatus | None = None


@dataclass(frozen=True, slots=True)
class ProjectDeletionContext:
    project_id: uuid.UUID
    project_name: str
    scan_ids: tuple[uuid.UUID, ...]
    active_scan_ids: tuple[uuid.UUID, ...]


ProjectSortBy = Literal[
    "created_at",
    "name",
    "owner",
    "scan_count",
    "scan_duration",
]
ProjectSortOrder = Literal["asc", "desc"]


@dataclass(frozen=True)
class AdminProjectListFilters:
    page: int = 1
    limit: int = 20
    sort_by: ProjectSortBy = "created_at"
    sort_order: ProjectSortOrder = "desc"
    query: str | None = None


class ProjectTimelinePoint(BaseModel):
    date: date
    count: int


class ProjectTimelineResponse(BaseModel):
    points: list[ProjectTimelinePoint]


@dataclass(frozen=True)
class AdminProjectRow:
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    repo_owner: str
    repo_name: str
    branch: str
    created_at: datetime
    updated_at: datetime
    owner_id: uuid.UUID
    owner_username: str
    owner_email: str
    scan_count: int
    average_scan_duration_seconds: float | None


class AdminProjectOwner(BaseModel):
    id: uuid.UUID
    username: str
    email: str


class AdminProjectResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    repo_owner: str
    repo_name: str
    branch: str
    created_at: datetime
    updated_at: datetime
    owner: AdminProjectOwner
    scan_count: int
    average_scan_duration_seconds: float | None


@dataclass(frozen=True)
class AdminProjectListResult:
    items: list[AdminProjectResponse]
    total_count: int
