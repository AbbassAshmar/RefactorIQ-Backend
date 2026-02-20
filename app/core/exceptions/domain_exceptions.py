from __future__ import annotations

from typing import Any


class DomainException(Exception):
    """Base exception for all domain-layer errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ValidationError(DomainException):
    """Domain validation failed."""

    def __init__(
        self,
        message: str = "Validation failed",
        field_errors: dict[str, list[str]] | None = None,
    ):
        super().__init__(message=message, details={"fields": field_errors or {}})


class AuthenticationError(DomainException):
    """Authentication failed or credentials are missing/invalid."""


class AuthorizationError(DomainException):
    """Authenticated actor is not allowed to perform this operation."""


class EntityNotFoundError(DomainException):
    """A required domain entity does not exist."""

    def __init__(
        self,
        entity_type: str,
        entity_id: Any | None = None,
        message: str | None = None,
    ):
        details: dict[str, Any] = {"entity_type": entity_type}
        if entity_id is not None:
            details["entity_id"] = str(entity_id)
        super().__init__(
            message=message or f"{entity_type.capitalize()} not found",
            details=details,
        )


class ConflictError(DomainException):
    """Operation conflicts with current state of resource(s)."""


class ExternalServiceError(DomainException):
    """A dependent external service failed to fulfill a request."""

    def __init__(
        self,
        service: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        merged = {"service": service}
        if details:
            merged.update(details)
        super().__init__(message=message, details=merged)