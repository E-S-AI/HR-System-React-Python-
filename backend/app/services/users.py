from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_pin, hash_secret
from app.models import Employee, Role, User
from app.schemas.user import UserCreate , StaffCreate

PRIVILEGED = {"CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR"}


def is_admin(user: User) -> bool:
    return user.is_super_admin or "CENTRAL_ADMIN" in {r.code for r in user.roles}

def is_privileged(user: User) -> bool:
    return user.is_super_admin or bool({r.code for r in user.roles} & PRIVILEGED)

async def get_manageable_user(db: AsyncSession, actor: User, user_id: int) -> User:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="الحساب غير موجود")
    target_roles = {r.code for r in target.roles}
    if (target.is_super_admin or target_roles & PRIVILEGED) and not is_admin(actor):
        raise HTTPException(
            status_code=403, detail="لا تملك صلاحية التعديل على حسابات المسؤولين"
        )
    return target


async def create_employee_account(
    db: AsyncSession, actor: User, data: UserCreate
) -> tuple[User, str]:
    employee = await db.get(Employee, data.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    if await db.scalar(select(User.id).where(User.employee_id == employee.id)):
        raise HTTPException(status_code=409, detail="لهذا الموظف حساب مسبقاً")

    role = await db.scalar(select(Role).where(Role.code == "EMPLOYEE"))
    if role is None:
        raise HTTPException(status_code=500, detail="دور الموظف غير موجود، شغّل seed")

    pin = generate_pin()
    user = User(
        phone_number=(data.phone_number or employee.phone_number).strip(),
        password_hash=await hash_secret(data.password),
        static_login_pin_hash=await hash_secret(pin),
        pin_generated_at=datetime.now(timezone.utc),
        employee_id=employee.id,
        created_by_user_id=actor.id,
    )
    user.roles.append(role)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="رقم الهاتف مستخدم لحساب آخر")
    return user, pin


async def reset_password(
    db: AsyncSession, actor: User, user_id: int, new_password: str
) -> None:
    target = await get_manageable_user(db, actor, user_id)
    target.password_hash = await hash_secret(new_password)
    target.password_reset_by_user_id = actor.id
    target.password_reset_at = datetime.now(timezone.utc)
    target.failed_login_attempts = 0
    target.locked_until = None
    await db.commit()


async def reset_pin(db: AsyncSession, actor: User, user_id: int) -> str:
    target = await get_manageable_user(db, actor, user_id)
    if target.require_google_auth:
        raise HTTPException(
            status_code=400, detail="هذا الحساب يدخل بـ Google Authenticator ولا رمز ثابت له"
        )
    pin = generate_pin()
    target.static_login_pin_hash = await hash_secret(pin)
    target.pin_generated_at = datetime.now(timezone.utc)
    target.pin_reset_by_user_id = actor.id
    target.failed_login_attempts = 0
    target.locked_until = None
    await db.commit()
    return pin


async def unlock(db: AsyncSession, actor: User, user_id: int) -> None:
    target = await get_manageable_user(db, actor, user_id)
    target.failed_login_attempts = 0
    target.locked_until = None
    await db.commit()


async def set_active(
    db: AsyncSession, actor: User, user_id: int, active: bool
) -> User:
    if user_id == actor.id:
        raise HTTPException(status_code=400, detail="لا يمكنك تعطيل حسابك بنفسك")
    target = await get_manageable_user(db, actor, user_id)
    target.is_active = active
    await db.commit()
    return target


async def create_staff_account(
    db: AsyncSession, actor: User, data: StaffCreate
) -> tuple[User, str]:
    role = await db.scalar(select(Role).where(Role.code == data.role_code))
    if role is None:
        raise HTTPException(status_code=422, detail="الدور غير موجود، شغّل seed")
    if data.employee_id is not None:
        employee = await db.get(Employee, data.employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="الموظف غير موجود")
        if await db.scalar(select(User.id).where(User.employee_id == employee.id)):
            raise HTTPException(status_code=409, detail="لهذا الموظف حساب مسبقاً")

    pin = generate_pin()  # مؤقت: لأول دخول وتفعيل Google Authenticator فقط
    user = User(
        phone_number=data.phone_number.strip(),
        password_hash=await hash_secret(data.password),
        static_login_pin_hash=await hash_secret(pin),
        pin_generated_at=datetime.now(timezone.utc),
        employee_id=data.employee_id,
        created_by_user_id=actor.id,
    )
    user.roles.append(role)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="رقم الهاتف مستخدم لحساب آخر")
    return user, pin


async def reset_2fa(db: AsyncSession, actor: User, user_id: int) -> str:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="الحساب غير موجود")
    if target.id == actor.id:
        raise HTTPException(status_code=400, detail="لا يمكنك إعادة تعيين مصادقتك بنفسك")
    if not target.require_google_auth:
        raise HTTPException(status_code=400, detail="المصادقة الثنائية غير مفعلة لهذا الحساب")

    pin = generate_pin()
    target.require_google_auth = False
    target.google_auth_secret_encrypted = None
    target.static_login_pin_hash = await hash_secret(pin)
    target.pin_generated_at = datetime.now(timezone.utc)
    target.pin_reset_by_user_id = actor.id
    target.failed_login_attempts = 0
    target.locked_until = None
    await db.commit()
    return pin