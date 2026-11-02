import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_ph = PasswordHasher()
_fernet = Fernet(settings.encryption_key.encode())
DUMMY_HASH = _ph.hash("dummy-password")


async def hash_secret(plain: str) -> str:
    return await asyncio.to_thread(_ph.hash, plain)


async def verify_secret(hashed: str, plain: str) -> bool:
    try:
        return await asyncio.to_thread(_ph.verify, hashed, plain)
    except (VerificationError, InvalidHashError):
        return False


def generate_pin() -> str:
    return f"{secrets.randbelow(10**6):06d}"


# ---------- JWT ----------
def create_access_token(user_id: int, scope: str = "full") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "scp": scope,  # full | enroll
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> tuple[int, str] | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return int(payload["sub"]), payload.get("scp", "full")
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


# ---------- التشفير (لأسرار Google Authenticator) ----------
def encrypt_text(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()


def decrypt_text(token: str, ttl: int | None = None) -> str | None:
    try:
        return _fernet.decrypt(token.encode(), ttl=ttl).decode()
    except InvalidToken:
        return None


# ---------- TOTP ----------
def new_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    # valid_window=1 يسمح بفارق ±30 ثانية في الساعة
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def totp_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name="HRMS")