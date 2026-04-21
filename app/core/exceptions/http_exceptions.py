from typing import Any


class HttpException(Exception):
    def __init__(self, status_code: int, message: str, details: dict[str, Any] | None = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class HttpUnauthorized(HttpException):
    """401 Unauthorized error."""
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(status_code=401, message=message)


class HttpForbidden(HttpException):
    """403 Forbidden error."""
    def __init__(self, message: str = "Forbidden"):
        super().__init__(status_code=403, message=message)


class HttpBadRequest(HttpException):
    """400 Bad Request error."""

    def __init__(self, message: str = "Bad request"):
        super().__init__(status_code=400, message=message)


class HttpNotFound(HttpException):
    """404 Not Found error."""

    def __init__(self, message: str = "Not found"):
        super().__init__(status_code=404, message=message)


class HttpBadGateway(HttpException):
    """502 Bad Gateway error."""

    def __init__(self, message: str = "Bad gateway"):
        super().__init__(status_code=502, message=message)
