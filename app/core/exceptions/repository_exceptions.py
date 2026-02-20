from __future__ import annotations

from typing import Any


class RepositoryException(Exception):
    """Base exception for repository/data-access failures."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class RecordNotFoundException(RepositoryException):
    """Requested record does not exist in persistence layer."""


class DuplicateRecordException(RepositoryException):
    """Operation violates uniqueness constraints."""


class DatabaseOperationException(RepositoryException):
    """Unexpected database-level operation failure."""
