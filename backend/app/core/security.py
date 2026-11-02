import asyncio
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

_ph = PasswordHasher()
DUMMY_HASH = _ph.hash("dummy-password")


async def hash_secret(plain: str) -> str:
    # التجزئة ثقيلة عمداً، فنشغلها في thread حتى لا تحجب الخادم
    return await asyncio.to_thread(_ph.hash, plain)


async def verify_secret(hashed: str, plain: str) -> bool:
    try:
        return await asyncio.to_thread(_ph.verify, hashed, plain)
    except (VerificationError, InvalidHashError):
        return False


def generate_pin() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None