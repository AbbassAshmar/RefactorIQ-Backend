"""Shared enums used across all layers (models, schemas, services)."""

import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CLIENT = "client"
