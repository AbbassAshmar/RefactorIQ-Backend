"""Password hashing / verification and Fernet encryption for tokens."""

from passlib.context import CryptContext
from cryptography.fernet import Fernet

from app.config import settings

# ── Password hashing ─────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ── Fernet encryption (GitHub access tokens) ─────────────────


def _get_fernet() -> Fernet:
    """Lazily create the Fernet instance (avoids import-time errors
    when the key hasn't been configured yet)."""
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_token(token: str) -> str:
    """Encrypt a plaintext token for safe database storage."""
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a previously encrypted token."""
    return _get_fernet().decrypt(encrypted_token.encode()).decode()
