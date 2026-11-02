import asyncio
import getpass
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.core.security import generate_pin, hash_secret
from app.models import Role, User


async def main() -> None:
    phone = input("Phone number: ").strip()
    password = getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("Password too short")
        return

    pin = generate_pin()
    async with SessionLocal() as db:
        if await db.scalar(select(User).where(User.phone_number == phone)):
            print("User already exists")
            return
        role = await db.scalar(select(Role).where(Role.code == "CENTRAL_ADMIN"))
        if role is None:
            print("Run: python -m app.seed first")
            return
        user = User(
            phone_number=phone,
            password_hash=await hash_secret(password),
            static_login_pin_hash=await hash_secret(pin),
            pin_generated_at=datetime.now(timezone.utc),
            is_super_admin=True,
        )
        user.roles.append(role)
        db.add(user)
        await db.commit()
    await engine.dispose()
    print(f"Admin created. Static PIN (shown once, write it down): {pin}")


if __name__ == "__main__":
    asyncio.run(main())