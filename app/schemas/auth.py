"""Authentication Pydantic schemas."""

from pydantic import BaseModel, EmailStr


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPayload(BaseModel):
    """Decoded JWT payload."""

    sub: str  # user id
    role: str


class AuthResponse(BaseModel):
    message: str
    user_id: str
    role: str
