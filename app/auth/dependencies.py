"""Auth dependency helpers.

Authentication/authorization utility functions live in ``app.auth.utils``.
This module is reserved for auth dependency wiring if needed.
"""

from app.auth.utils import COOKIE_NAME

__all__ = ["COOKIE_NAME"]
