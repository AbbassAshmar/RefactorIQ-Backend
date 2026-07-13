"""Authentication request, token, and response DTOs."""

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, field_validator

from app.config import settings


def _validate_admin_email(value: str) -> str:
    """Validate admin login emails, including the development seed address.

    ``email-validator`` intentionally rejects special-use domains such as
    ``.local``. The development seeder uses one of those domains because the
    address is only a login identifier, so validate its syntax against a
    normal TLD while retaining the original domain for the database lookup.
    """
    value = value.strip()

    try:
        return validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        if settings.ENVIRONMENT.lower() == "development":
            local_part, separator, domain = value.rpartition("@")
            if separator and domain.lower().endswith(".local"):
                candidate_domain = f"{domain[:-len('.local')]}.com"
                try:
                    normalized = validate_email(
                        f"{local_part}@{candidate_domain}",
                        check_deliverability=False,
                    ).normalized
                except EmailNotValidError:
                    pass
                else:
                    normalized_local_part, _, _ = normalized.rpartition("@")
                    return f"{normalized_local_part}@{domain.lower()}"

        raise ValueError(str(exc)) from exc


class AdminLoginRequest(BaseModel):
    email: str
    password: str

    _validate_email = field_validator("email")(_validate_admin_email)


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: str
    role: str


class AuthResponse(BaseModel):
    message: str
    user_id: str
    role: str
