from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, EmployeeAssignment, User
from app.schemas.employee_files import AssignmentEnd, AssignmentInput
from app.services.assignment_rules import duration_text, end_date_error, renewal_date_error
from app.services.employee_helpers import add_log, locked_employee
from app.services.leave_balances import visible_employee


def _bad(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _summary(a: EmployeeAssignment) -> str:
    end = a.end_date.isoformat() if a.end_date else "-"
    return f"#{a.sequence_number} {a.action_type} من {a.start_date.isoformat()} إلى {end}"


async def _current(db: AsyncSession, employee_id: int) -> EmployeeAssignment | None:
    return await db.scalar(
        select(EmployeeAssignment).where(
            EmployeeAssignment.employee_id == employee_id,
            EmployeeAssignment.is_current.is_(True),
        )
    )


async def _next_seq(db: AsyncSession, employee_id: int) -> int:
    top = await db.scalar(
        select(func.coalesce(func.max(EmployeeAssignment.sequence_number), 0)).where(
            EmployeeAssignment.employee_id == employee_id
        )
    )
    return top + 1


async def _baseline(db: AsyncSession, emp: Employee, actor: User) -> EmployeeAssignment | None:
    """تكليف مخزَّن في ملف الموظف بلا سطر في الأرشيف (مستورد): ننشئ له سطراً قبل تجديده أو إنهائه."""
    if emp.assignment_start_date is None:
        return None
    end = emp.assignment_end_date
    if end is not None and end < emp.assignment_start_date:
        end = None
    row = EmployeeAssignment(
        employee_id=emp.id,
        sequence_number=await _next_seq(db, emp.id),
        action_type="INITIAL_ASSIGNMENT",
        start_date=emp.assignment_start_date,
        end_date=end,
        duration_text=emp.assignment_duration,
        is_current=True,
        notes="أُنشئ من بيانات التكليف المخزنة في ملف الموظف",
        created_by_hr_id=actor.id,
    )
    db.add(row)
    await db.flush()
    return row


def _apply_to_employee(emp: Employee, start, end, duration) -> None:
    emp.assignment_start_date = start
    emp.assignment_end_date = end
    emp.assignment_duration = duration


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _bad(409, "تعذّر حفظ التكليف بسبب تعارض في البيانات، أعد المحاولة")


async def list_assignments(
    db: AsyncSession, actor: User, employee_id: int
) -> list[EmployeeAssignment]:
    await visible_employee(db, actor, employee_id)
    rows = await db.scalars(
        select(EmployeeAssignment)
        .where(EmployeeAssignment.employee_id == employee_id)
        .order_by(EmployeeAssignment.sequence_number)
    )
    return list(rows.all())


async def start_assignment(
    db: AsyncSession, actor: User, employee_id: int, data: AssignmentInput
) -> EmployeeAssignment:
    emp = await locked_employee(db, actor, employee_id)
    if await _current(db, emp.id) is not None or emp.assignment_start_date is not None:
        raise _bad(409, "يوجد تكليف حالي لهذا الموظف، استخدم التجديد أو الإنهاء")
    duration = data.duration_text or duration_text(data.start_date, data.end_date)
    row = EmployeeAssignment(
        employee_id=emp.id,
        sequence_number=await _next_seq(db, emp.id),
        action_type="INITIAL_ASSIGNMENT",
        start_date=data.start_date,
        end_date=data.end_date,
        duration_text=duration,
        assigned_position_or_unit=data.assigned_position_or_unit,
        decision_number=data.decision_number,
        is_current=True,
        notes=data.notes,
        created_by_hr_id=actor.id,
    )
    db.add(row)
    _apply_to_employee(emp, data.start_date, data.end_date, duration)
    emp.updated_by_hr_id = actor.id
    await db.flush()
    add_log(db, emp.id, actor.id, "assignment:INITIAL_ASSIGNMENT", None, _summary(row), data.notes)
    await _commit(db)
    return row


async def renew_assignment(
    db: AsyncSession, actor: User, employee_id: int, data: AssignmentInput
) -> EmployeeAssignment:
    emp = await locked_employee(db, actor, employee_id)
    cur = await _current(db, emp.id) or await _baseline(db, emp, actor)
    if cur is None:
        raise _bad(409, "لا يوجد تكليف حالي لتجديده، ابدأ تكليفاً أولاً")
    error = renewal_date_error(cur.start_date, cur.end_date, data.start_date)
    if error:
        await db.rollback()
        raise _bad(422, error)

    old = _summary(cur)
    cur.is_current = False
    await db.flush()  # يحرر الفهرس الفريد قبل إضافة الجديد

    duration = data.duration_text or duration_text(data.start_date, data.end_date)
    row = EmployeeAssignment(
        employee_id=emp.id,
        sequence_number=await _next_seq(db, emp.id),
        action_type="RENEWAL",
        start_date=data.start_date,
        end_date=data.end_date,
        duration_text=duration,
        assigned_position_or_unit=data.assigned_position_or_unit,
        decision_number=data.decision_number,
        is_current=True,
        notes=data.notes,
        created_by_hr_id=actor.id,
    )
    db.add(row)
    _apply_to_employee(emp, data.start_date, data.end_date, duration)
    emp.assignment_renewal_count = (emp.assignment_renewal_count or 0) + 1
    emp.updated_by_hr_id = actor.id
    await db.flush()
    add_log(db, emp.id, actor.id, "assignment:RENEWAL", old, _summary(row), data.notes)
    await _commit(db)
    return row


async def end_assignment(
    db: AsyncSession, actor: User, employee_id: int, data: AssignmentEnd
) -> EmployeeAssignment:
    emp = await locked_employee(db, actor, employee_id)
    cur = await _current(db, emp.id) or await _baseline(db, emp, actor)
    if cur is None:
        raise _bad(409, "لا يوجد تكليف حالي لإنهائه")
    error = end_date_error(cur.start_date, data.end_date)
    if error:
        await db.rollback()
        raise _bad(422, error)

    old = _summary(cur)
    cur.is_current = False
    cur.end_date = data.end_date  # الإنهاء الفعلي يحل محل الانتهاء المخطط
    await db.flush()

    row = EmployeeAssignment(
        employee_id=emp.id,
        sequence_number=await _next_seq(db, emp.id),
        action_type="ENDED",
        start_date=data.end_date,
        end_date=data.end_date,
        decision_number=data.decision_number,
        is_current=False,
        notes=data.notes,
        created_by_hr_id=actor.id,
    )
    db.add(row)
    _apply_to_employee(emp, None, None, None)
    emp.updated_by_hr_id = actor.id
    await db.flush()
    add_log(db, emp.id, actor.id, "assignment:ENDED", old, _summary(row), data.notes)
    await _commit(db)
    return row