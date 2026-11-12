import asyncio
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Employee,
    LeaveApprovalLog,
    LeaveBalance,
    LeaveRequest,
    LeaveTransaction,
    LeaveType,
    User,
    WorkSchedule,
)
from app.schemas.leave_request import (
    DECISION_LEAVE_TYPES,
    HRDirectDecisionCreate,
    LeaveRequestCreate,
    LeaveRequestRead,
)
from app.services.holidays import load_holidays
from app.services.leave_balances import visible_employee
from app.services.leave_rules import (
    add_months,
    admin_minutes,
    charged_hourly_minutes,
    consecutive_run_over_limit,
    is_too_old,
    is_workday,
    minutes_between,
    overlaps,
    schedule_for,
    working_days,
)
from app.services.scope import get_scope
from app.services.users import is_privileged

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("AWAITING_PAPER", "PENDING_HR_APPROVAL", "APPROVED")
MAX_PAPER_BYTES = 8 * 1024 * 1024


def local_tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ مساعدات
def _log(db, req_id, actor_id, from_s, to_s, action, comment=None) -> None:
    db.add(
        LeaveApprovalLog(
            leave_request_id=req_id,
            actor_user_id=actor_id,
            from_status=from_s,
            to_status=to_s,
            action_type=action,
            comment=comment,
        )
    )


def _set_status(db, req: LeaveRequest, new: str, actor_id, action, comment=None) -> None:
    old = req.status
    req.status = new
    _log(db, req.id, actor_id, old, new, action, comment)


async def _schedules_between(db: AsyncSession, start: date, end: date) -> list[WorkSchedule]:
    rows = await db.scalars(
        select(WorkSchedule).where(
            WorkSchedule.effective_from_date <= end,
            (WorkSchedule.effective_to_date.is_(None))
            | (WorkSchedule.effective_to_date >= start),
        )
    )
    return list(rows.all())


def _bad(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _plan_request(lt: LeaveType, data: LeaveRequestCreate, schedules, holidays) -> dict:
    """يحسب التواريخ والأوقات والمدة حسب نوع الطلب."""
    start = data.start_date
    end = data.end_date or start

    if lt.code == "ADMIN":
        try:
            minutes, days = admin_minutes(schedules, start, end, holidays)
        except ValueError as exc:
            raise _bad(409, str(exc))
        if not days:
            raise _bad(422, "كل أيام الفترة المختارة عطلة (أسبوعية أو رسمية)")
        return {
            "start": days[0],
            "end": days[-1],
            "start_time": schedule_for(schedules, days[0]).official_start_time,
            "end_time": schedule_for(schedules, days[-1]).official_end_time,
            "minutes": minutes,
            "days": Decimal(len(days)),
            "day_list": days,
        }

    if lt.code == "HOURLY":
        if end != start:
            raise _bad(422, "الإجازة الساعية تكون ضمن يوم واحد")
        if not is_workday(start, holidays):
            raise _bad(422, "اليوم المختار عطلة أسبوعية أو رسمية")
        sch = schedule_for(schedules, start)
        if sch is None:
            raise _bad(409, f"لا يوجد جدول دوام ساري بتاريخ {start.isoformat()}")
        if data.start_time is None or data.end_time is None:
            raise _bad(422, "حدد وقت بداية ونهاية الإجازة الساعية")
        st = data.start_time.replace(second=0, microsecond=0)
        et = data.end_time.replace(second=0, microsecond=0)
        if st < sch.official_start_time or et > sch.official_end_time:
            raise _bad(
                422,
                "يجب أن تقع الإجازة الساعية ضمن ساعات الدوام "
                f"({sch.official_start_time:%H:%M} - {sch.official_end_time:%H:%M})",
            )
        lo, hi = lt.min_duration_minutes, lt.max_duration_minutes
        try:
            # أقل من ساعة تُحسب ساعة كاملة، وأكثر من ساعتين مرفوض
            minutes = charged_hourly_minutes(minutes_between(st, et), lo, hi)
        except ValueError as exc:
            if str(exc) == "over_max":
                raise _bad(422, f"الإجازة الساعية لا تزيد عن {hi} دقيقة (ساعتان)")
            raise _bad(422, str(exc))
        return {
            "start": start,
            "end": end,
            "start_time": st,
            "end_time": et,
            "minutes": minutes,
            "days": (Decimal(minutes) / Decimal(sch.workday_minutes)).quantize(
                Decimal("0.01")
            ),
        }

    if lt.code == "MISSION":
        if data.start_time is None or data.end_time is None:
            raise _bad(422, "حدد وقت بداية ونهاية المهمة")
        st = data.start_time.replace(second=0, microsecond=0)
        et = data.end_time.replace(second=0, microsecond=0)
        s_dt, e_dt = datetime.combine(start, st), datetime.combine(end, et)
        if e_dt <= s_dt:
            raise _bad(422, "نهاية المهمة يجب أن تكون بعد بدايتها")
        return {
            "start": start,
            "end": end,
            "start_time": st,
            "end_time": et,
            "minutes": int((e_dt - s_dt).total_seconds() // 60),
            "days": Decimal((end - start).days + 1),
        }

    raise _bad(422, "نوع الطلب غير مدعوم")


def _window(r: LeaveRequest) -> tuple[datetime, datetime]:
    return (
        datetime.combine(r.start_date, r.start_time),
        datetime.combine(r.end_date, r.end_time),
    )


# ------------------------------------------------------------------ حجز الرصيد
async def _reserve_tx(db: AsyncSession, request_id: int) -> LeaveTransaction | None:
    return await db.scalar(
        select(LeaveTransaction).where(
            LeaveTransaction.leave_request_id == request_id,
            LeaveTransaction.transaction_type == "RESERVE",
        )
    )


async def _release(db: AsyncSession, req: LeaveRequest, actor_id, note: str) -> None:
    reserve = await _reserve_tx(db, req.id)
    if reserve is None:  # طلب لا يخصم من الرصيد (مهمة)
        return
    balance = await db.scalar(
        select(LeaveBalance).where(LeaveBalance.id == reserve.balance_id).with_for_update()
    )
    minutes = -reserve.delta_minutes
    balance.reserved_minutes -= minutes
    db.add(
        LeaveTransaction(
            balance_id=balance.id,
            leave_request_id=req.id,
            transaction_type="RELEASE",
            delta_minutes=minutes,
            notes=note[:255],
            created_by_user_id=actor_id,
        )
    )


async def _deduct(db: AsyncSession, req: LeaveRequest, actor_id) -> None:
    reserve = await _reserve_tx(db, req.id)
    if reserve is None:
        return
    balance = await db.scalar(
        select(LeaveBalance).where(LeaveBalance.id == reserve.balance_id).with_for_update()
    )
    minutes = -reserve.delta_minutes
    balance.reserved_minutes -= minutes
    balance.used_minutes += minutes
    # المتبقي لا يتغير عند تحويل الحجز إلى خصم، لذا القيمة صفر
    db.add(
        LeaveTransaction(
            balance_id=balance.id,
            leave_request_id=req.id,
            transaction_type="DEDUCT",
            delta_minutes=0,
            notes="تحويل الحجز إلى خصم بعد اعتماد الموارد البشرية",
            created_by_user_id=actor_id,
        )
    )


# ------------------------------------------------------------------ إنشاء الطلب
async def create_request(db: AsyncSession, user: User, data: LeaveRequestCreate) -> int:
    if user.employee_id is None:
        raise _bad(403, "حسابك غير مرتبط بسجل موظف")

    # قفل صف الموظف يسلسل طلباته المتزامنة (يمنع تجاوز الرصيد والتداخل بطلبين معاً)
    employee = await db.scalar(
        select(Employee).where(Employee.id == user.employee_id).with_for_update(key_share=True)
    )

    lt = await db.scalar(
        select(LeaveType).where(LeaveType.code == data.leave_type_code, LeaveType.is_active)
    )
    if lt is None or not lt.allow_employee_request:
        raise _bad(422, "نوع الطلب غير متاح")

    start = data.start_date
    end = data.end_date or start
    schedules = await _schedules_between(db, start, end)
    holidays = await load_holidays(db, start - timedelta(days=60), end + timedelta(days=60))
    plan = _plan_request(lt, data, schedules, holidays)
    # المتعاقد لا يحق له إجازة إدارية أو ساعية في أول أشهر من بدء العمل بالدولة
    if lt.deducts_balance and employee.permanent_or_contract == "متعاقد":
        months = settings.contract_admin_leave_wait_months
        eligible_from = add_months(employee.state_start_date, months)
        if plan["start"] < eligible_from:
            raise _bad(
                422,
                f"لا يحق للموظف المتعاقد إجازة إدارية أو ساعية خلال أول {months} أشهر "
                f"من بدء العمل بالدولة، ويبدأ استحقاقه بتاريخ {eligible_from.isoformat()}",
            )

    tz = local_tz()
    now_local = datetime.now(tz)
    now_utc = utcnow()
    new_start = datetime.combine(plan["start"], plan["start_time"])
    new_end = datetime.combine(plan["end"], plan["end_time"])

    if lt.enforce_72h_rule:
        max_hours = lt.max_past_entry_hours or 72
        if is_too_old(new_start.replace(tzinfo=tz), now_local, max_hours):
            raise _bad(422, f"لا يُقبل طلب تاريخ بدايته أقدم من {max_hours} ساعة")

    if lt.deducts_balance and plan["start"].year != plan["end"].year:
        raise _bad(422, "يجب أن يقع الطلب ضمن سنة تقويمية واحدة، قدّمه على طلبين")

    # منع التداخل مع أي طلب فعّال
    others = await db.scalars(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == user.employee_id,
            LeaveRequest.status.in_(ACTIVE_STATUSES),
            LeaveRequest.start_date <= plan["end"],
            LeaveRequest.end_date >= plan["start"],
        )
    )
    for other in others.all():
        o_start, o_end = _window(other)
        if overlaps(new_start, new_end, o_start, o_end):
            raise _bad(409, f"يتعارض مع طلبك رقم {other.id} (الحالة: {other.status})")

    # الإدارية: لا أكثر من N أيام عمل متتالية (مع احتساب الطلبات المجاورة)
    if lt.code == "ADMIN":
        limit = settings.max_consecutive_admin_days
        existing = await db.scalars(
            select(LeaveRequest)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveRequest.employee_id == user.employee_id,
                LeaveType.code == "ADMIN",
                LeaveRequest.status.in_(ACTIVE_STATUSES),
                LeaveRequest.start_date <= plan["end"] + timedelta(days=14),
                LeaveRequest.end_date >= plan["start"] - timedelta(days=14),
            )
        )
        old_days = [
            d for r in existing.all() for d in working_days(r.start_date, r.end_date, holidays)
        ]
        over = consecutive_run_over_limit(plan["day_list"], old_days, limit, holidays)
        if over is not None:
            first_day, length = over
            raise _bad(
                422,
                f"لا يجوز أن تزيد الإجازة الإدارية عن {limit} أيام عمل متتالية "
                f"(مع احتساب طلباتك المجاورة تصبح {length} أيام ابتداءً من {first_day.isoformat()})",
            )

    balance = None
    minutes = plan["minutes"]
    if lt.deducts_balance:
        balance_type_id = lt.deducts_from_type_id or lt.id
        year = plan["start"].year
        balance = await db.scalar(
            select(LeaveBalance)
            .where(
                LeaveBalance.employee_id == user.employee_id,
                LeaveBalance.leave_type_id == balance_type_id,
                LeaveBalance.year == year,
            )
            .with_for_update()
        )
        if balance is None:
            raise _bad(409, f"لا يوجد رصيد إجازات لسنة {year}، راجع الموارد البشرية")
        available = balance.entitled_minutes - balance.used_minutes - balance.reserved_minutes
        if minutes > available:
            raise _bad(
                409,
                f"رصيدك غير كافٍ: المطلوب {minutes} دقيقة والمتاح {available} دقيقة",
            )

    deadline = (
        now_utc + timedelta(hours=lt.paper_upload_grace_hours or 72)
        if lt.enforce_72h_rule
        else None
    )
    req = LeaveRequest(
        employee_id=user.employee_id,
        leave_type_id=lt.id,
        entry_source="EMPLOYEE_PORTAL",
        start_date=plan["start"],
        end_date=plan["end"],
        start_time=plan["start_time"],
        end_time=plan["end_time"],
        duration_days=plan["days"],
        duration_minutes=minutes,
        reason=data.reason,
        status="AWAITING_PAPER",
        attachment_deadline_at=deadline,
        created_by_user_id=user.id,
        created_at=now_utc,
    )
    db.add(req)
    await db.flush()
    _log(db, req.id, user.id, None, "AWAITING_PAPER", "SUBMIT")
    if balance is not None:
        balance.reserved_minutes += minutes
        db.add(
            LeaveTransaction(
                balance_id=balance.id,
                leave_request_id=req.id,
                transaction_type="RESERVE",
                delta_minutes=-minutes,
                notes=f"حجز لطلب رقم {req.id}",
                created_by_user_id=user.id,
            )
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _bad(409, "تعذّر حفظ الطلب بسبب تعارض في البيانات، أعد المحاولة")
    return req.id


# ------------------------------------------------------------------ الوصول والقراءة
async def _own_request(
    db: AsyncSession, user: User, request_id: int, lock: bool = False
) -> LeaveRequest:
    if user.employee_id is None:
        raise _bad(404, "الطلب غير موجود")
    stmt = select(LeaveRequest).where(
        LeaveRequest.id == request_id, LeaveRequest.employee_id == user.employee_id
    )
    if lock:
        stmt = stmt.with_for_update()
    req = await db.scalar(stmt)
    if req is None:
        raise _bad(404, "الطلب غير موجود")
    return req


async def get_visible(db: AsyncSession, user: User, request_id: int) -> LeaveRequest:
    """صاحب الطلب، أو HR ضمن نطاقه. غير ذلك: غير موجود."""
    req = await db.get(LeaveRequest, request_id)
    if req is None:
        raise _bad(404, "الطلب غير موجود")
    if user.employee_id is not None and user.employee_id == req.employee_id:
        return req
    if is_privileged(user):
        await visible_employee(db, user, req.employee_id)
        return req
    raise _bad(404, "الطلب غير موجود")


def to_read(r: LeaveRequest, lt: LeaveType, emp: Employee) -> LeaveRequestRead:
    return LeaveRequestRead(
        id=r.id,
        employee_id=r.employee_id,
        employee_name=emp.full_name_spaced,
        employee_code=emp.employee_code,
        leave_type_code=lt.code,
        leave_type_name_ar=lt.name_ar,
        entry_source=r.entry_source,
        start_date=r.start_date,
        end_date=r.end_date,
        start_time=r.start_time,
        end_time=r.end_time,
        duration_days=float(r.duration_days),
        duration_minutes=r.duration_minutes,
        reason=r.reason,
        status=r.status,
        paper_uploaded=bool(r.paper_attachment_path),
        attachment_uploaded_at=r.attachment_uploaded_at,
        attachment_deadline_at=r.attachment_deadline_at,
        hr_reviewer_id=r.hr_reviewer_id,
        hr_action_at=r.hr_action_at,
        hr_notes=r.hr_notes,
        hr_decision_number=r.hr_decision_number,
        created_at=r.created_at,
    )


def _base_select():
    return (
        select(LeaveRequest, LeaveType, Employee)
        .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
        .join(Employee, Employee.id == LeaveRequest.employee_id)
    )


async def fetch_read(db: AsyncSession, request_id: int) -> LeaveRequestRead:
    row = (await db.execute(_base_select().where(LeaveRequest.id == request_id))).first()
    if row is None:
        raise _bad(404, "الطلب غير موجود")
    return to_read(*row)


async def list_mine(
    db: AsyncSession,
    user: User,
    status: str | None,
    year: int | None,
    skip: int,
    limit: int,
) -> list[LeaveRequestRead]:
    if user.employee_id is None:
        raise _bad(404, "حسابك غير مرتبط بسجل موظف")
    stmt = _base_select().where(LeaveRequest.employee_id == user.employee_id)
    if status:
        stmt = stmt.where(LeaveRequest.status == status)
    if year:
        stmt = stmt.where(
            LeaveRequest.start_date >= date(year, 1, 1),
            LeaveRequest.start_date <= date(year, 12, 31),
        )
    rows = (
        await db.execute(stmt.order_by(LeaveRequest.id.desc()).offset(skip).limit(limit))
    ).all()
    return [to_read(*r) for r in rows]


async def list_for_hr(
    db: AsyncSession,
    actor: User,
    employee_id: int | None,
    status: str | None,
    leave_type_code: str | None,
    date_from: date | None,
    date_to: date | None,
    skip: int,
    limit: int,
) -> list[LeaveRequestRead]:
    stmt = _base_select()
    scope = await get_scope(db, actor)
    if scope is not None:
        stmt = stmt.where(scope.employee_filter())
    if employee_id:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    if status:
        stmt = stmt.where(LeaveRequest.status == status)
    if leave_type_code:
        stmt = stmt.where(LeaveType.code == leave_type_code)
    if date_from:
        stmt = stmt.where(LeaveRequest.end_date >= date_from)
    if date_to:
        stmt = stmt.where(LeaveRequest.start_date <= date_to)
    rows = (
        await db.execute(stmt.order_by(LeaveRequest.id.desc()).offset(skip).limit(limit))
    ).all()
    return [to_read(*r) for r in rows]


async def list_logs(db: AsyncSession, request_id: int) -> list[LeaveApprovalLog]:
    rows = await db.scalars(
        select(LeaveApprovalLog)
        .where(LeaveApprovalLog.leave_request_id == request_id)
        .order_by(LeaveApprovalLog.id)
    )
    return list(rows.all())


# ------------------------------------------------------------------ الورقة الموقعة
def detect_paper_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith(b"%PDF-"):
        return ".pdf"
    return None


def paper_abs(rel: str) -> Path:
    base = Path(settings.upload_dir).resolve()
    path = (base / rel).resolve()
    if base not in path.parents:
        raise _bad(404, "الملف غير موجود")
    return path


def _validate_paper(content: bytes) -> str:
    if not content:
        raise _bad(422, "الملف فارغ")
    if len(content) > MAX_PAPER_BYTES:
        raise _bad(413, "حجم الملف يتجاوز 8 ميغابايت")
    ext = detect_paper_type(content)
    if ext is None:
        raise _bad(422, "الملف يجب أن يكون صورة (JPG أو PNG) أو PDF")
    return ext


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


async def _auto_reject_one(db: AsyncSession, req: LeaveRequest) -> None:
    await _release(db, req, None, f"تحرير الحجز: انتهت مهلة رفع الورقة للطلب رقم {req.id}")
    _set_status(
        db, req, "AUTO_REJECTED_72H_NO_PAPER", None, "AUTO_REJECT_72H",
        "انتهت مهلة رفع الورقة الموقعة",
    )


async def upload_paper(
    db: AsyncSession, user: User, request_id: int, content: bytes
) -> None:
    req = await _own_request(db, user, request_id, lock=True)
    if req.status not in ("AWAITING_PAPER", "PENDING_HR_APPROVAL"):
        raise _bad(409, f"لا يمكن رفع ورقة لطلب حالته {req.status}")

    now = utcnow()
    if (
        req.status == "AWAITING_PAPER"
        and req.attachment_deadline_at is not None
        and now > req.attachment_deadline_at
    ):
        await _auto_reject_one(db, req)
        await db.commit()
        raise _bad(409, "انتهت مهلة رفع الورقة (72 ساعة) وتم رفض الطلب آلياً")

    ext = _validate_paper(content)
    rel = f"leave_papers/{req.id}_{uuid.uuid4().hex[:12]}{ext}"
    path = paper_abs(rel)
    await asyncio.to_thread(_write_bytes, path, content)
    old = req.paper_attachment_path
    try:
        req.paper_attachment_path = rel
        req.attachment_uploaded_at = now
        _set_status(db, req, "PENDING_HR_APPROVAL", user.id, "UPLOAD_SIGNED_PAPER")
        await db.commit()
    except Exception:
        await db.rollback()
        path.unlink(missing_ok=True)
        raise
    if old and old != rel:
        try:
            paper_abs(old).unlink(missing_ok=True)
        except Exception:
            logger.warning("could not delete old paper %s", old)


# ------------------------------------------------------------------ الإلغاء والقرارات
async def cancel_request(db: AsyncSession, user: User, request_id: int) -> None:
    req = await _own_request(db, user, request_id, lock=True)
    if req.status not in ("AWAITING_PAPER", "PENDING_HR_APPROVAL"):
        raise _bad(409, f"لا يمكن إلغاء طلب حالته {req.status}")
    await _release(db, req, user.id, f"إلغاء الطلب رقم {req.id} من الموظف")
    _set_status(db, req, "CANCELLED_BY_EMPLOYEE", user.id, "CANCEL_BY_EMPLOYEE")
    await db.commit()


async def hr_decide(
    db: AsyncSession,
    actor: User,
    request_id: int,
    approve: bool,
    notes: str | None,
    decision_number: str | None,
) -> None:
    req = await db.scalar(
        select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update()
    )
    if req is None:
        raise _bad(404, "الطلب غير موجود")
    await visible_employee(db, actor, req.employee_id)  # يرفض الطلب خارج النطاق بـ 404
    if actor.employee_id is not None and actor.employee_id == req.employee_id:
        raise _bad(403, "لا يمكنك اعتماد أو رفض طلبك الشخصي")
    if req.status != "PENDING_HR_APPROVAL":
        raise _bad(409, f"حالة الطلب ({req.status}) لا تسمح بهذا الإجراء")
    if approve and not req.paper_attachment_path:
        raise _bad(409, "لا توجد ورقة موقعة مرفوعة لهذا الطلب")

    if approve:
        await _deduct(db, req, actor.id)
        new_status, action = "APPROVED", "HR_APPROVE"
    else:
        await _release(db, req, actor.id, f"رفض الطلب رقم {req.id} من الموارد البشرية")
        new_status, action = "REJECTED_BY_HR", "HR_REJECT"

    req.hr_reviewer_id = actor.id
    req.hr_action_at = utcnow()
    req.hr_notes = (notes or "").strip() or None
    req.hr_decision_number = (decision_number or "").strip() or None if approve else None
    _set_status(db, req, new_status, actor.id, action, req.hr_notes)
    await db.commit()


async def auto_reject_overdue(db: AsyncSession) -> int:
    """يرفض الطلبات التي انتهت مهلة ورقتها. آمن التكرار ويصلح لـ Celery Beat."""
    total = 0
    while True:
        rows = (
            await db.scalars(
                select(LeaveRequest)
                .where(
                    LeaveRequest.status == "AWAITING_PAPER",
                    LeaveRequest.attachment_deadline_at.is_not(None),
                    LeaveRequest.attachment_deadline_at < utcnow(),
                )
                .order_by(LeaveRequest.id)
                .limit(200)
                .with_for_update(skip_locked=True)
            )
        ).all()
        if not rows:
            break
        for req in rows:
            await _auto_reject_one(db, req)
        await db.commit()
        total += len(rows)
    return total


# ------------------------------------------------------------------ قرارات الموارد البشرية المباشرة
async def create_hr_decision(
    db: AsyncSession, actor: User, data: HRDirectDecisionCreate, content: bytes
) -> int:
    """تسجيل إجازة بقرار (بلا أجر، مرضية، زواج، وفاة، حج) معتمدة مباشرة دون خصم من الرصيد."""
    ext = _validate_paper(content)
    await visible_employee(db, actor, data.employee_id)  # خارج النطاق => 404
    if actor.employee_id is not None and actor.employee_id == data.employee_id:
        raise _bad(403, "لا يمكنك تسجيل قرار إجازة لنفسك")

    # قفل صف الموظف يسلسل الطلبات المتزامنة ويمنع التداخل
    employee = await db.scalar(
        select(Employee).where(Employee.id == data.employee_id).with_for_update(key_share=True)
    )
    if employee is None:
        raise _bad(404, "الموظف غير موجود")

    lt = await db.scalar(
        select(LeaveType).where(LeaveType.code == data.leave_type_code, LeaveType.is_active)
    )
    if lt is None or lt.code not in DECISION_LEAVE_TYPES:
        raise _bad(422, "نوع الإجازة غير متاح")

    start, end = data.start_date, data.end_date
    schedules = await _schedules_between(db, start, end)
    holidays = await load_holidays(db, start, end)
    first_sch, last_sch = schedule_for(schedules, start), schedule_for(schedules, end)
    start_time = first_sch.official_start_time if first_sch else time(0, 0)
    end_time = last_sch.official_end_time if last_sch else time(23, 59)
    # دقائق الدوام المغطاة بالقرار (للتقارير فقط، لا خصم من الرصيد)
    minutes = 0
    for d in working_days(start, end, holidays):
        sch = schedule_for(schedules, d)
        if sch is not None:
            minutes += sch.workday_minutes

    new_start = datetime.combine(start, start_time)
    new_end = datetime.combine(end, end_time)
    others = await db.scalars(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == data.employee_id,
            LeaveRequest.status.in_(ACTIVE_STATUSES),
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )
    )
    for other in others.all():
        o_start, o_end = _window(other)
        if overlaps(new_start, new_end, o_start, o_end):
            raise _bad(
                409,
                f"يتعارض مع الطلب رقم {other.id} (الحالة: {other.status})، "
                "عالجه أولاً ثم سجّل القرار",
            )

    now = utcnow()
    req = LeaveRequest(
        employee_id=data.employee_id,
        leave_type_id=lt.id,
        entry_source="HR_DIRECT_DECISION",
        start_date=start,
        end_date=end,
        start_time=start_time,
        end_time=end_time,
        duration_days=Decimal((end - start).days + 1),
        duration_minutes=minutes,
        reason=data.reason,
        status="APPROVED",
        hr_decision_number=data.hr_decision_number,
        hr_reviewer_id=actor.id,
        hr_action_at=now,
        hr_notes=data.notes,
        attachment_uploaded_at=now,
        created_by_user_id=actor.id,
        created_at=now,
    )
    db.add(req)
    await db.flush()
    request_id = req.id

    rel = f"leave_papers/{request_id}_decision_{uuid.uuid4().hex[:12]}{ext}"
    path = paper_abs(rel)
    await asyncio.to_thread(_write_bytes, path, content)
    try:
        req.paper_attachment_path = rel
        comment = f"قرار رقم {data.hr_decision_number}"
        if data.notes:
            comment += f" - {data.notes}"
        _log(db, request_id, actor.id, None, "APPROVED", "HR_DIRECT_DECISION", comment)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        path.unlink(missing_ok=True)
        raise _bad(409, "تعذّر حفظ القرار بسبب تعارض في البيانات، أعد المحاولة")
    except Exception:
        await db.rollback()
        path.unlink(missing_ok=True)
        raise
    return request_id
