from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LeaveRequest, LeaveType, PublicHoliday, User
from app.schemas.holiday import HolidayCreate
from app.services.leave_rules import iter_days

ACTIVE = ("AWAITING_PAPER", "PENDING_HR_APPROVAL", "APPROVED")


async def load_holidays(db: AsyncSession, start: date, end: date) -> frozenset[date]:
    rows = await db.scalars(
        select(PublicHoliday.holiday_date).where(
            PublicHoliday.holiday_date >= start, PublicHoliday.holiday_date <= end
        )
    )
    return frozenset(rows.all())


async def list_holidays(db: AsyncSession, year: int) -> list[PublicHoliday]:
    rows = await db.scalars(
        select(PublicHoliday)
        .where(
            PublicHoliday.holiday_date >= date(year, 1, 1),
            PublicHoliday.holiday_date <= date(year, 12, 31),
        )
        .order_by(PublicHoliday.holiday_date)
    )
    return list(rows.all())


async def _affected_requests(db: AsyncSession, days: list[date]) -> list[int]:
    """طلبات إدارية/ساعية فعّالة تشمل أياماً صارت عطلة رسمية (للمراجعة اليدوية)."""
    if not days:
        return []
    rows = (
        await db.execute(
            select(LeaveRequest.id, LeaveRequest.start_date, LeaveRequest.end_date)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveType.code.in_(("ADMIN", "HOURLY")),
                LeaveRequest.status.in_(ACTIVE),
                LeaveRequest.start_date <= max(days),
                LeaveRequest.end_date >= min(days),
            )
            .order_by(LeaveRequest.id)
            .limit(500)
        )
    ).all()
    return [rid for rid, s, e in rows if any(s <= d <= e for d in days)]


async def create_holidays(db: AsyncSession, actor: User, data: HolidayCreate):
    days = list(iter_days(data.date_from, data.date_to or data.date_from))
    existing = set(
        (
            await db.scalars(
                select(PublicHoliday.holiday_date).where(
                    PublicHoliday.holiday_date.in_(days)
                )
            )
        ).all()
    )
    new_days = [d for d in days if d not in existing]
    created = [
        PublicHoliday(
            holiday_date=d, name_ar=data.name_ar.strip(), created_by_user_id=actor.id
        )
        for d in new_days
    ]
    db.add_all(created)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="أحد التواريخ أُضيف للتو من مستخدم آخر، أعد المحاولة"
        )
    return created, sorted(existing), await _affected_requests(db, new_days)


async def delete_holiday(db: AsyncSession, holiday_id: int) -> None:
    holiday = await db.get(PublicHoliday, holiday_id)
    if holiday is None:
        raise HTTPException(status_code=404, detail="العطلة غير موجودة")
    await db.delete(holiday)
    await db.commit()