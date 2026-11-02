from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import DUMMY_HASH, decrypt_text, verify_secret, verify_totp
from app.models import User
from app.services.users import is_privileged

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15


def _invalid() -> HTTPException:
    return HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")


async def authenticate(
    db: AsyncSession,
    phone_number: str,
    password: str,
    pin: str | None,
    otp: str | None,
) -> tuple[User, str]:
    user = await db.scalar(
        select(User).where(User.phone_number == phone_number).with_for_update()
    )
    if user is None:
        await verify_secret(DUMMY_HASH, password)
        raise _invalid()

    now = datetime.now(timezone.utc)
    if not user.is_active:
        raise _invalid()
    if user.locked_until and user.locked_until > now:
        raise HTTPException(
            status_code=423,
            detail="الحساب مقفل مؤقتاً بسبب محاولات خاطئة، حاول لاحقاً أو راجع الموارد البشرية",
        )

    ok = await verify_secret(user.password_hash, password)
    if ok:
        if user.require_google_auth:
            secret = (
                decrypt_text(user.google_auth_secret_encrypted)
                if user.google_auth_secret_encrypted
                else None
            )
            ok = otp is not None and secret is not None and verify_totp(secret, otp)
        else:
            ok = (
                pin is not None
                and user.static_login_pin_hash is not None
                and await verify_secret(user.static_login_pin_hash, pin)
            )

    if not ok:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_login_attempts = 0
        await db.commit()
        raise _invalid()

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    await db.commit()

    # حساب إداري لم يفعّل Google Authenticator بعد => توكن للتفعيل فقط
    scope = "enroll" if is_privileged(user) and not user.require_google_auth else "full"
    return user, scope