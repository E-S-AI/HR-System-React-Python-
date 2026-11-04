from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models import User
from app.schemas.leave_balance import (
    AdjustRequest,
    BalanceRead,
    GrantRequest,
    GrantResult,
    RecalcRequest,
    TransactionRead,
)
from app.services import leave_balances as svc

router = APIRouter(prefix="/leave-balances", tags=["leave-balances"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")
admin_only = require_roles("CENTRAL_ADMIN")


@router.get("/me", response_model=list[BalanceRead])
async def my_balances(
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.employee_id is None:
        raise HTTPException(status_code=404, detail="حسابك غير مرتبط بسجل موظف")
    return await svc.list_balances(db, user.employee_id, year or date.today().year)


@router.get("", response_model=list[BalanceRead])
async def employee_balances(
    employee_id: int,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    await svc.visible_employee(db, actor, employee_id)
    return await svc.list_balances(db, employee_id, year or date.today().year)


@router.get("/{balance_id}/transactions", response_model=list[TransactionRead])
async def balance_transactions(
    balance_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    await svc.balance_with_employee(db, actor, balance_id)
    return await svc.list_transactions(db, balance_id)


@router.post("/grants", response_model=GrantResult)
async def run_grant(
    data: GrantRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_only),
):
    created, mpd = await svc.grant_year(db, data.year, data.employee_id, actor.id)
    return GrantResult(year=data.year, created=created, minutes_per_day=mpd)


@router.post("/recalculate", response_model=BalanceRead)
async def recalculate(
    data: RecalcRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.recalculate(db, actor, data.employee_id, data.year)


@router.post("/adjust", response_model=BalanceRead)
async def adjust(
    data: AdjustRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.adjust(
        db, actor, data.employee_id, data.year, data.delta_minutes, data.notes
    )