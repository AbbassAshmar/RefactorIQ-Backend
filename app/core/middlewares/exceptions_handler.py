import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions.domain_exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DomainException,
    EntityNotFoundError,
    ExternalServiceError,
    ValidationError,
)
from app.utils.response import ApiResponse

logger = logging.getLogger(__name__)


EXCEPTION_MAPPINGS = {
    ValidationError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR"),
    AuthenticationError: (status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED"),
    AuthorizationError: (status.HTTP_403_FORBIDDEN, "FORBIDDEN"),
    EntityNotFoundError: (status.HTTP_404_NOT_FOUND, "NOT_FOUND"),
    ConflictError: (status.HTTP_409_CONFLICT, "CONFLICT"),
    ExternalServiceError: (status.HTTP_502_BAD_GATEWAY, "EXTERNAL_SERVICE_ERROR"),
}


async def domain_exception_handler(
    request: Request, exc: DomainException
) -> JSONResponse:
    exc_type = type(exc)
    if exc_type in EXCEPTION_MAPPINGS:
        status_code, error_code = EXCEPTION_MAPPINGS[exc_type]
        message = exc.message
        details = exc.details
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        error_code = "INTERNAL_ERROR"
        message = "An internal server error occurred"
        details = None

    return ApiResponse.error(
        code=error_code,
        message=message,
        status_code=status_code,
        details=details,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    field_errors: dict[str, list[str]] = {}
    for error in exc.errors():
        field = ".".join(str(x) for x in error["loc"][1:])
        field_errors.setdefault(field, []).append(error["msg"])

    return ApiResponse.error(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"fields": field_errors},
    )


async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return ApiResponse.error(
        code="INTERNAL_ERROR",
        message="An internal server error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(DomainException, domain_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)