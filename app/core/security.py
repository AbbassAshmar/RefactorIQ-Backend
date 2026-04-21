"""Password hashing / verification and token encryption utilities."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from passlib.context import CryptContext

from app.config import settings

# ── Password hashing ─────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# ── Token encryption (GitHub access tokens) ─────────────────

AES_GCM_PREFIX = "aesgcm:v1:"
AES_GCM_NONCE_SIZE = 12


def _decode_base64_key(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded)


def _get_key_bytes() -> bytes:
    """Resolve a 32-byte AES key from ENCRYPTION_KEY in the environment."""
    key_bytes = _decode_base64_key(settings.ENCRYPTION_KEY)
    if len(key_bytes) != 32:
        raise ValueError("ENCRYPTION_KEY must be base64url for exactly 32 bytes")
    return key_bytes


def _get_aesgcm() -> AESGCM:
    return AESGCM(_get_key_bytes())


def encrypt_token(token: str) -> str:
    """Encrypt a plaintext token using AES-256-GCM for database storage."""
    nonce = os.urandom(AES_GCM_NONCE_SIZE)
    ciphertext = _get_aesgcm().encrypt(nonce, token.encode(), None)
    payload = base64.urlsafe_b64encode(nonce + ciphertext).decode()
    return f"{AES_GCM_PREFIX}{payload}"


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an AES-256-GCM encrypted token payload."""
    if not encrypted_token.startswith(AES_GCM_PREFIX):
        raise ValueError("Invalid encrypted token format")

    encoded_payload = encrypted_token[len(AES_GCM_PREFIX) :]
    payload = _decode_base64_key(encoded_payload)

    if len(payload) <= AES_GCM_NONCE_SIZE:
        raise ValueError("Invalid AES-GCM token payload")

    nonce = payload[:AES_GCM_NONCE_SIZE]
    ciphertext = payload[AES_GCM_NONCE_SIZE:]
    plaintext = _get_aesgcm().decrypt(nonce, ciphertext, None)
    return plaintext.decode()
