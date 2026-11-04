from datetime import date, time, timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, WorkSchedule
from app.schemas.work_schedule import WorkScheduleCreate


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _to_time(m: int) -> time:
    return time(m // 60, m % 60)


async def schedule_on(db: AsyncSession, day: date) -> WorkSchedule | None:
    return await db.scalar(
        select(WorkSchedule).where(
            WorkSchedule.effective_from_date <= day,
            or_(
                WorkSchedule.effective_to_date.is_(None),
                WorkSchedule.effective_to_date >= day,
            ),
        )
    )


async def create_schedule(
    db: AsyncSession, actor: User, data: WorkScheduleCreate
) -> WorkSchedule:
    start = _minutes(data.official_start_time)
    end = _minutes(data.official_end_time)
    late_cut = start + data.late_grace_minutes
    early_cut = end - data.early_leave_grace_minutes
    if late_cut >= early_cut:
        raise HTTPException(
            status_code=422,
            detail="مهلتا التأخير والانصراف المبكر تتجاوزان طول الدوام",
        )

    # الجدول المفتوح (بلا تاريخ نهاية) يُغلق في اليوم السابق لبدء الجدول الجديد
    open_ = await db.scalar(
        select(WorkSchedule).where(WorkSchedule.effective_to_date.is_(None)).with_for_update()
    )
    if open_ is not None and data.effective_from_date > open_.effective_from_date:
        open_.effective_to_date = data.effective_from_date - timedelta(days=1)
        await db.flush()

    schedule = WorkSchedule(
        schedule_name_ar=data.schedule_name_ar.strip(),
        official_start_time=_to_time(start),
        official_end_time=_to_time(end),
        late_grace_minutes=data.late_grace_minutes,
        early_leave_grace_minutes=data.early_leave_grace_minutes,
        late_cutoff_time=_to_time(late_cut),
        early_leave_cutoff_time=_to_time(early_cut),
        workday_minutes=end - start,
        effective_from_date=data.effective_from_date,
        effective_to_date=data.effective_to_date,
        updated_by_user_id=actor.id,
    )
    db.add(schedule)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="يتداخل هذا الجدول زمنياً مع جدول دوام آخر أو يبدأ في تاريخ يبدأ فيه جدول موجود",
        )
    await db.refresh(schedule)
    return schedule