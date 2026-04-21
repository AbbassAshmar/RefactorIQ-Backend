from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class RoleInternal(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)
