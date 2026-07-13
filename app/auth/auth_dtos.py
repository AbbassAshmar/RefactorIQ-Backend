"""Authentication request, token, and response DTOs."""

from pydantic import BaseModel, EmailStr


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: str
    role: str


class AuthResponse(BaseModel):
    message: str
    user_id: str
    role: str
