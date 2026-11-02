import segno
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    decrypt_text,
    encrypt_text,
    new_totp_secret,
    totp_uri,
    verify_totp,
)
from app.models import User
from app.services.users import is_privileged

SETUP_TTL_SECONDS = 600


def begin_setup(user: User) -> dict:
    if not is_privileged(user):
        raise HTTPException(
            status_code=403,
            detail="المصادقة الثنائية مخصصة لحسابات الإدارة والموارد البشرية",
        )
    if user.require_google_auth:
        raise HTTPException(
            status_code=400,
            detail="المصادقة الثنائية مفعلة مسبقاً، اطلب من مسؤول النظام إعادة تعيينها",
        )
    secret = new_totp_secret()
    uri = totp_uri(secret, user.phone_number)
    return {
        "setup_token": encrypt_text(f"{user.id}:{secret}"),
        "secret": secret,
        "otpauth_uri": uri,
        "qr_svg_data_uri": segno.make(uri, error="m").svg_data_uri(scale=6, border=2),
    }


async def confirm_setup(
    db: AsyncSession, user: User, setup_token: str, code: str
) -> None:
    if user.require_google_auth:
        raise HTTPException(status_code=400, detail="المصادقة الثنائية مفعلة مسبقاً")
    plain = decrypt_text(setup_token, ttl=SETUP_TTL_SECONDS)
    if plain is None:
        raise HTTPException(
            status_code=400, detail="انتهت صلاحية رمز التفعيل، ابدأ الإعداد من جديد"
        )
    user_id, _, secret = plain.partition(":")
    if user_id != str(user.id):
        raise HTTPException(status_code=400, detail="رمز التفعيل لا يخص هذا الحساب")
    if not verify_totp(secret, code):
        raise HTTPException(status_code=400, detail="الرمز غير صحيح، تأكد من ساعة هاتفك")

    user.google_auth_secret_encrypted = encrypt_text(secret)
    user.require_google_auth = True
    user.static_login_pin_hash = None  # لا طريق التفافي بالرمز الثابت بعد التفعيل
    user.pin_generated_at = None
    user.failed_login_attempts = 0
    await db.commit()