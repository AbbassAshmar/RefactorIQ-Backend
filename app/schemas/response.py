# app/schemas/responses.py
from typing import Optional, Dict, Any, Generic, TypeVar
from pydantic import BaseModel, Field
from datetime import datetime

T = TypeVar('T')


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total_pages: int
    total_count: int
    has_next_page: bool
    has_previous_page: bool


class ResponseMeta(BaseModel):
    pagination: Optional[PaginationMeta] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    error: Optional[ErrorDetail] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
    data: Optional[Any] = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

    