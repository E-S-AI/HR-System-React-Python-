from datetime import date

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Employee,
    LeaveBalance,
    LeaveTransaction,
    LeaveType,
    ServiceLeaveTier,
    User,
)
from app.schemas.leave_balance import BalanceRead
from app.services.leave_calc import completed_years, pick_tier, service_years_decimal
from app.services.scope import get_scope
from app.services.work_schedules import schedule_on

BATCH = 500


async def visible_employee(db: AsyncSession, actor: User, employee_id: int) -> Employee:
    employee = await db.get(Employee, employee_id)
    scope = await get_scope(db, actor)
    if employee is None or (
        scope is not None
        and not scope.allows(employee.governorate_code, employee.org_unit_id)
    ):
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    return employee


async def _admin_type(db: AsyncSession) -> LeaveType:
    leave_type = await db.scalar(select(LeaveType).where(LeaveType.code == "ADMIN"))
    if leave_type is None:
        raise HTTPException(status_code=500, detail="نوع الإجازة الإدارية غير موجود، شغّل seed")
    return leave_type


async def _tiers(db: AsyncSession, type_id: int) -> list[ServiceLeaveTier]:
    rows = await db.scalars(
        select(ServiceLeaveTier)
        .where(ServiceLeaveTier.leave_type_id == type_id)
        .order_by(ServiceLeaveTier.min_service_years)
    )
    tiers = list(rows.all())
    if not tiers:
        raise HTTPException(status_code=409, detail="شرائح الإجازة الإدارية غير معرّفة، شغّل seed")
    return tiers


def to_read(b: LeaveBalance, t: LeaveType) -> BalanceRead:
    remaining = b.entitled_minutes - b.used_minutes - b.reserved_minutes
    return BalanceRead(
        id=b.id,
        employee_id=b.employee_id,
        leave_type_code=t.code,
        leave_type_name_ar=t.name_ar,
        year=b.year,
        service_years_snapshot=float(b.service_years_snapshot),
        minutes_per_day=b.minutes_per_day,
        entitled_minutes=b.entitled_minutes,
        used_minutes=b.used_minutes,
        reserved_minutes=b.reserved_minutes,
        remaining_minutes=remaining,
        remaining_days=round(remaining / b.minutes_per_day, 2),
    )


async def list_balances(db: AsyncSession, employee_id: int, year: int) -> list[BalanceRead]:
    rows = (
        await db.execute(
            select(LeaveBalance, LeaveType)
            .join(LeaveType, LeaveType.id == LeaveBalance.leave_type_id)
            .where(LeaveBalance.employee_id == employee_id, LeaveBalance.year == year)
            .order_by(LeaveType.id)
        )
    ).all()
    return [to_read(b, t) for b, t in rows]


async def balance_with_employee(db: AsyncSession, actor: User, balance_id: int) -> LeaveBalance:
    balance = await db.get(LeaveBalance, balance_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="الرصيد غير موجود")
    await visible_employee(db, actor, balance.employee_id)
    return balance


async def list_transactions(db: AsyncSession, balance_id: int) -> list[LeaveTransaction]:
    rows = await db.scalars(
        select(LeaveTransaction)
        .where(LeaveTransaction.balance_id == balance_id)
        .order_by(LeaveTransaction.id)
    )
    return list(rows.all())


# ------------------------------------------------------------------ المنح السنوي
async def grant_year(
    db: AsyncSession, year: int, employee_id: int | None, actor_id: int | None
) -> tuple[int, int]:
    admin = await _admin_type(db)
    tiers = await _tiers(db, admin.id)
    ref = date(year, 1, 1)
    schedule = await schedule_on(db, ref)
    if schedule is None:
        raise HTTPException(
            status_code=409, detail=f"لا يوجد جدول دوام ساري في 1 يناير {year}"
        )
    mpd = schedule.workday_minutes

    pending = (
        select(Employee.id, Employee.state_start_date)
        .where(
            Employee.state_start_date <= date(year, 12, 31),
            or_(Employee.termination_date.is_(None), Employee.termination_date >= ref),
            ~exists().where(
                LeaveBalance.employee_id == Employee.id,
                LeaveBalance.leave_type_id == admin.id,
                LeaveBalance.year == year,
            ),
        )
        .order_by(Employee.id)
        .limit(BATCH)
    )
    if employee_id is not None:
        pending = pending.where(Employee.id == employee_id)

    created = 0
    while True:
        rows = (await db.execute(pending)).all()
        if not rows:
            break
        values = []
        for emp_id, start in rows:
            tier = pick_tier(tiers, completed_years(start, ref))
            if tier is None:
                raise HTTPException(status_code=409, detail="شرائح الخدمة لا تغطي كل المدد")
            values.append(
                {
                    "employee_id": emp_id,
                    "leave_type_id": admin.id,
                    "year": year,
                    "service_years_snapshot": service_years_decimal(start, ref),
                    "minutes_per_day": mpd,
                    "entitled_minutes": tier.entitled_days * mpd,
                }
            )
        inserted = (
            await db.execute(
                insert(LeaveBalance)
                .values(values)
                .on_conflict_do_nothing(
                    index_elements=["employee_id", "leave_type_id", "year"]
                )
                .returning(LeaveBalance.id, LeaveBalance.entitled_minutes)
            )
        ).all()
        if inserted:
            await db.execute(
                insert(LeaveTransaction),
                [
                    {
                        "balance_id": bid,
                        "transaction_type": "ANNUAL_GRANT",
                        "delta_minutes": minutes,
                        "notes": f"منح سنوي {year}",
                        "created_by_user_id": actor_id,
                    }
                    for bid, minutes in inserted
                ],
            )
        await db.commit()
        created += len(inserted)
    return created, mpd


# ------------------------------------------------------------------ إعادة الاحتساب والتسوية
async def _locked_balance(
    db: AsyncSession, employee_id: int, leave_type_id: int, year: int
) -> LeaveBalance:
    balance = await db.scalar(
        select(LeaveBalance)
        .where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
            LeaveBalance.year == year,
        )
        .with_for_update()
    )
    if balance is None:
        raise HTTPException(
            status_code=404, detail="لا يوجد رصيد لهذه السنة، شغّل المنح السنوي أولاً"
        )
    return balance


async def recalculate(
    db: AsyncSession, actor: User, employee_id: int, year: int
) -> BalanceRead:
    employee = await visible_employee(db, actor, employee_id)
    admin = await _admin_type(db)
    tiers = await _tiers(db, admin.id)
    balance = await _locked_balance(db, employee.id, admin.id, year)

    ref = date(year, 1, 1)
    tier = pick_tier(tiers, completed_years(employee.state_start_date, ref))
    if tier is None:
        raise HTTPException(status_code=409, detail="شرائح الخدمة لا تغطي هذه المدة")
    expected = tier.entitled_days * balance.minutes_per_day
    granted = await db.scalar(
        select(func.coalesce(func.sum(LeaveTransaction.delta_minutes), 0)).where(
            LeaveTransaction.balance_id == balance.id,
            LeaveTransaction.transaction_type == "ANNUAL_GRANT",
        )
    )
    diff = expected - granted
    balance.service_years_snapshot = service_years_decimal(employee.state_start_date, ref)
    if diff != 0:
        if balance.entitled_minutes + diff < 0:
            await db.rollback()
            raise HTTPException(
                status_code=409, detail="إعادة الاحتساب تجعل الاستحقاق سالباً، راجع الحركات"
            )
        db.add(
            LeaveTransaction(
                balance_id=balance.id,
                transaction_type="ANNUAL_GRANT",
                delta_minutes=diff,
                notes="إعادة احتساب الشريحة بعد تعديل تاريخ بدء العمل بالدولة",
                created_by_user_id=actor.id,
            )
        )
        balance.entitled_minutes += diff
    await db.commit()
    await db.refresh(balance)
    return to_read(balance, admin)


async def adjust(
    db: AsyncSession,
    actor: User,
    employee_id: int,
    year: int,
    delta_minutes: int,
    notes: str,
) -> BalanceRead:
    if delta_minutes == 0:
        raise HTTPException(status_code=422, detail="قيمة التسوية يجب ألا تكون صفراً")
    await visible_employee(db, actor, employee_id)
    admin = await _admin_type(db)
    balance = await _locked_balance(db, employee_id, admin.id, year)
    if balance.entitled_minutes + delta_minutes < 0:
        await db.rollback()
        raise HTTPException(status_code=409, detail="التسوية تجعل الاستحقاق سالباً")
    db.add(
        LeaveTransaction(
            balance_id=balance.id,
            transaction_type="HR_ADJUSTMENT",
            delta_minutes=delta_minutes,
            notes=notes.strip(),
            created_by_user_id=actor.id,
        )
    )
    balance.entitled_minutes += delta_minutes
    await db.commit()
    await db.refresh(balance)
    return to_read(balance, admin)