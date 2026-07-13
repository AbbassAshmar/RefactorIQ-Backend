import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CLIENT = "client"


class ScanStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"