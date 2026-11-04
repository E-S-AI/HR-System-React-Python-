from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import User, WorkSchedule
from app.schemas.work_schedule import WorkScheduleCreate, WorkScheduleRead
from app.services import work_schedules as svc

router = APIRouter(prefix="/work-schedules", tags=["work-schedules"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")
admin_only = require_roles("CENTRAL_ADMIN")


@router.get("", response_model=list[WorkScheduleRead])
async def list_schedules(
    db: AsyncSession = Depends(get_db), _: User = Depends(hr_or_admin)
):
    rows = await db.scalars(
        select(WorkSchedule).order_by(WorkSchedule.effective_from_date)
    )
    return rows.all()


@router.get("/current", response_model=WorkScheduleRead)
async def current_schedule(
    db: AsyncSession = Depends(get_db), _: User = Depends(hr_or_admin)
):
    schedule = await svc.schedule_on(db, date.today())
    if schedule is None:
        raise HTTPException(status_code=404, detail="لا يوجد جدول دوام ساري اليوم")
    return schedule


@router.post("", response_model=WorkScheduleRead, status_code=201)
async def create_schedule(
    data: WorkScheduleCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_only),
):
    return await svc.create_schedule(db, actor, data)