"""Scan request, response, and pipeline DTOs."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
