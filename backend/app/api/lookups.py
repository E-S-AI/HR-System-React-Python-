from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles , get_current_user
from app.core.database import get_db
from app.models import AppointmentCategory, Governorate, User , LeaveType

router = APIRouter(prefix="/lookups", tags=["lookups"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")


class CategoryRead(BaseModel):
    code: str
    label_ar: str
    employment_type: str


class GovernorateRead(BaseModel):
    code: str
    name_ar: str
    name_en: str


@router.get("/appointment-categories", response_model=list[CategoryRead])
async def appointment_categories(
    employment_type: str | None = Query(None, description="مثبت أو متعاقد"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(hr_or_admin),
):
    stmt = select(AppointmentCategory).order_by(AppointmentCategory.id)
    if employment_type:
        stmt = stmt.where(AppointmentCategory.employment_type == employment_type)
    rows = (await db.scalars(stmt)).all()
    return [
        CategoryRead(
            code=c.category_code,
            label_ar=c.category_label_ar,
            employment_type=c.employment_type,
        )
        for c in rows
    ]


@router.get("/governorates", response_model=list[GovernorateRead])
async def governorates(
    db: AsyncSession = Depends(get_db), _: User = Depends(hr_or_admin)
):
    rows = (await db.scalars(select(Governorate).order_by(Governorate.id))).all()
    return [
        GovernorateRead(
            code=g.governorate_code,
            name_ar=g.governorate_name_ar,
            name_en=g.governorate_name_en,
        )
        for g in rows
    ]

class LeaveTypeRead(BaseModel):
    code: str
    name_ar: str
    allow_employee_request: bool
    deducts_balance: bool
    min_duration_minutes: int | None
    max_duration_minutes: int | None
    enforce_72h_rule: bool


@router.get("/leave-types", response_model=list[LeaveTypeRead])
async def leave_types(
    db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    rows = await db.scalars(
        select(LeaveType).where(LeaveType.is_active).order_by(LeaveType.id)
    )
    return [
        LeaveTypeRead(
            code=t.code,
            name_ar=t.name_ar,
            allow_employee_request=t.allow_employee_request,
            deducts_balance=t.deducts_balance,
            min_duration_minutes=t.min_duration_minutes,
            max_duration_minutes=t.max_duration_minutes,
            enforce_72h_rule=t.enforce_72h_rule,
        )
        for t in rows.all()
    ]