"""Scan request, response, and pipeline DTOs."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import ScanStatus


class ScanCreate(BaseModel):
    project_id: int


class ScanResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScanUserResponse(BaseModel):
    id: uuid.UUID
    github_username: str
    github_access_token: str | None

    model_config = ConfigDict(from_attributes=True)


class ScanProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    repo_owner: str
    repo_name: str
    branch: str
    user_id: uuid.UUID
    user: ScanUserResponse

    model_config = ConfigDict(from_attributes=True)


class ScanProjectUserResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    project: ScanProjectResponse

    model_config = ConfigDict(from_attributes=True)


@dataclass(frozen=True)
class ScanListFilters:
    """Validated list criteria passed from the service to the repository."""

    user_id: uuid.UUID
    project_id: uuid.UUID | None = None
    status: str | None = None
    page: int = 1
    limit: int = 10
    sort_descending: bool = True


@dataclass(frozen=True)
class ScanListResult:
    items: list[ScanResponse]
    total_count: int


@dataclass(frozen=True)
class AdminScanListFilters:
    project_id: uuid.UUID | None = None
    status: ScanStatus | None = None
    page: int = 1
    limit: int = 10
    sort_descending: bool = True


@dataclass(frozen=True)
class AdminScanRow:
    id: uuid.UUID
    status: ScanStatus
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    project_id: uuid.UUID
    project_name: str
    owner_id: uuid.UUID
    owner_username: str
    owner_email: str


class AdminScanProject(BaseModel):
    id: uuid.UUID
    name: str


class AdminScanOwner(BaseModel):
    id: uuid.UUID
    username: str
    email: str


class AdminScanResponse(BaseModel):
    id: uuid.UUID
    status: ScanStatus
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    project: AdminScanProject
    owner: AdminScanOwner


@dataclass(frozen=True)
class AdminScanListResult:
    items: list[AdminScanResponse]
    total_count: int


@dataclass(frozen=True)
class FailedScanRow:
    id: uuid.UUID
    status: ScanStatus
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    project_id: uuid.UUID
    project_name: str
    user_id: uuid.UUID
    username: str


class ScanTimelinePoint(BaseModel):
    date: date
    count: int


class ScanTimelineResponse(BaseModel):
    granularity: str = "day"
    points: list[ScanTimelinePoint]


class ScanStatusCount(BaseModel):
    status: ScanStatus
    count: int


class ScanStatusDistributionResponse(BaseModel):
    statuses: list[ScanStatusCount]


class FailedScanProject(BaseModel):
    id: uuid.UUID
    name: str


class FailedScanUser(BaseModel):
    id: uuid.UUID
    username: str


class FailedScanResponse(BaseModel):
    id: uuid.UUID
    status: ScanStatus
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    project: FailedScanProject
    user: FailedScanUser
