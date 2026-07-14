from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import RefactorQueueStatus


class RefactorQueueCreate(BaseModel):
    project_id: uuid.UUID
    file_path: str = Field(min_length=1, max_length=4096)

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("file_path must not be blank")
        return value


class RefactorQueueMove(BaseModel):
    status: RefactorQueueStatus
    position: int = Field(ge=0)


class RefactorQueueItemResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    file_path: str
    status: RefactorQueueStatus
    position: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RefactorQueueListResponse(BaseModel):
    project_id: uuid.UUID
    items: list[RefactorQueueItemResponse]
