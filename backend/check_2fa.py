import asyncio
import sys

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.core.security import decrypt_text
from app.models import User


async def main(phone: str) -> None:
    async with SessionLocal() as db:
        u = await db.scalar(select(User).where(User.phone_number == phone))
        if u is None:
            print("user not found")
            return
        print("active:", u.is_active, "| 2fa enabled:", u.require_google_auth,
              "| has pin:", u.static_login_pin_hash is not None)
        print("failed attempts:", u.failed_login_attempts, "| locked until:", u.locked_until)
        if u.google_auth_secret_encrypted:
            ok = decrypt_text(u.google_auth_secret_encrypted) is not None
            print("secret decrypts with current ENCRYPTION_KEY:", ok)
    await engine.dispose()


asyncio.run(main(sys.argv[1]))