import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.core.security import generate_pin, hash_secret
from app.models import User


async def main() -> None:
    phone = input("Phone number: ").strip()
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.phone_number == phone))
        if user is None:
            print("User not found")
            return
        pin = generate_pin()
        user.require_google_auth = False
        user.google_auth_secret_encrypted = None
        user.static_login_pin_hash = await hash_secret(pin)
        user.pin_generated_at = datetime.now(timezone.utc)
        user.failed_login_attempts = 0
        user.locked_until = None
        await db.commit()
    await engine.dispose()
    print(f"2FA reset. Temporary PIN (login, then enroll again): {pin}")


if __name__ == "__main__":
    asyncio.run(main())