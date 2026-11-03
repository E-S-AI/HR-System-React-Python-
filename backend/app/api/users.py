from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import Employee, User
from app.schemas.user import (
    PasswordReset,
    PinResetResponse,
    StaffCreate,
    StatusUpdate,
    UserCreate,
    UserCreated,
    UserRead,
)
from app.services import users as svc
from app.services.scope import get_scope

router = APIRouter(prefix="/users", tags=["users"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")
admin_only = require_roles("CENTRAL_ADMIN")


def to_read(u: User) -> UserRead:
    return UserRead(
        id=u.id,
        phone_number=u.phone_number,
        employee_id=u.employee_id,
        is_active=u.is_active,
        locked_until=u.locked_until,
        last_login_at=u.last_login_at,
        roles=[r.code for r in u.roles],
    )


@router.post("", response_model=UserCreated, status_code=201)
async def create_account(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    user, pin = await svc.create_employee_account(db, actor, data)
    return UserCreated(
        id=user.id,
        phone_number=user.phone_number,
        employee_id=user.employee_id,
        static_pin=pin,
    )


@router.post("/staff", response_model=UserCreated, status_code=201)
async def create_staff(
    data: StaffCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_only),
):
    user, pin = await svc.create_staff_account(db, actor, data)
    return UserCreated(
        id=user.id,
        phone_number=user.phone_number,
        employee_id=user.employee_id,
        static_pin=pin,
    )


@router.get("", response_model=list[UserRead])
async def list_users(
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    stmt = select(User).order_by(User.id).offset(skip).limit(limit)
    scope = await get_scope(db, actor)
    if scope is not None:
        stmt = stmt.join(Employee, User.employee_id == Employee.id).where(
            scope.employee_filter()
        )
    rows = await db.scalars(stmt)
    return [to_read(u) for u in rows.all()]


@router.post("/{user_id}/reset-password", status_code=204)
async def reset_password(
    user_id: int,
    data: PasswordReset,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    await svc.reset_password(db, actor, user_id, data.new_password)


@router.post("/{user_id}/reset-pin", response_model=PinResetResponse)
async def reset_pin(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return PinResetResponse(static_pin=await svc.reset_pin(db, actor, user_id))


@router.post("/{user_id}/reset-2fa", response_model=PinResetResponse)
async def reset_2fa(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_only),
):
    return PinResetResponse(static_pin=await svc.reset_2fa(db, actor, user_id))


@router.post("/{user_id}/unlock", status_code=204)
async def unlock(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    await svc.unlock(db, actor, user_id)


@router.patch("/{user_id}/status", response_model=UserRead)
async def update_status(
    user_id: int,
    data: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return to_read(await svc.set_active(db, actor, user_id, data.is_active))