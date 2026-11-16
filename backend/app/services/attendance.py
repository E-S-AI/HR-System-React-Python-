"""
Attendance service: Excel/CSV import, Arabic name matching, daily evaluation engine,
BIOMETRIC_DEDUCT transaction creation.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import NamedTuple

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import norm_search, to_ascii_digits
from app.models import (
    Employee,
    LeaveBalance,
    LeaveRequest,
    LeaveTransaction,
    LeaveType,
    PublicHoliday,
    User,
    WorkSchedule,
)
from app.models.attendance import AttendanceRecord, AttendanceSyncLog, BiometricDevice
from app.services.excel_utils import read_table, norm_text, to_text, to_date, clean_cell
from app.services.work_schedules import schedule_on

# Weekend in Yemen: Friday + Saturday
_WEEKEND_DAYS = {4, 5}  # weekday() 4=Friday, 5=Saturday

# Column name aliases for the 7 platform columns (Arabic headers)
_COL_ALIASES: dict[str, str] = {
    "رقم الموظف": "biometric_user_id",
    "رقم البصمة": "biometric_user_id",
    "كود البصمة": "biometric_user_id",
    "الاسم": "biometric_employee_name",
    "اسم الموظف": "biometric_employee_name",
    "التاريخ": "attendance_date",
    "أول دخول": "first_in",
    "اول دخول": "first_in",
    "أول بصمة": "first_in",
    "آخر خروج": "last_out",
    "اخر خروج": "last_out",
    "آخر بصمة": "last_out",
    "الحالة": "platform_status",
    "الحالة بالنظام": "platform_status",
    "المديرية": "platform_directorate",
    "الوحدة": "platform_directorate",
}

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _map_headers(raw_headers: list) -> dict[int, str]:
    """Return {col_index: field_name} for recognised columns."""
    mapping: dict[int, str] = {}
    for idx, h in enumerate(raw_headers):
        if h is None:
            continue
        normed = norm_text(str(h))
        for arabic, field in _COL_ALIASES.items():
            if norm_text(arabic) == normed:
                mapping[idx] = field
                break
    return mapping


def _parse_time(v) -> time | None:
    """Parse a time value: accepts time, datetime, or HH:MM / HH:MM:SS strings."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, time):
        return v
    s = to_ascii_digits(str(v).strip())
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class ImportOutcome(NamedTuple):
    sync_log: AttendanceSyncLog
    unmapped: list[dict]
    errors: list[dict]


# ---------------------------------------------------------------------------
# Arabic name matching
# ---------------------------------------------------------------------------

class DayDecision(NamedTuple):
    """Pure result of comparing punches against a schedule's cutoffs."""
    late_minutes: int
    early_leave_minutes: int
    is_late_beyond_cutoff: bool
    is_early_leave_beyond_cutoff: bool
    gross_charged_minutes: int
    status: str


def compute_day(
    first_in: time | None,
    last_out: time | None,
    official_start: time,
    official_end: time,
    late_cutoff: time,
    early_cutoff: time,
) -> DayDecision:
    """
    Pure late/early calculation (no DB).

    late_minutes  = minutes first_in is after official_start.
    early_minutes = minutes last_out is before official_end.
    A cutoff is "crossed" when first_in >= late_cutoff / last_out <= early_cutoff.
    Only crossing a cutoff charges minutes; minutes are still reported otherwise.
    """
    late_min = 0
    early_min = 0
    is_late = False
    is_early = False

    if first_in is not None:
        start_secs = official_start.hour * 3600 + official_start.minute * 60
        in_secs = first_in.hour * 3600 + first_in.minute * 60
        late_min = max(0, (in_secs - start_secs) // 60)
        is_late = first_in >= late_cutoff

    if last_out is not None:
        end_secs = official_end.hour * 3600 + official_end.minute * 60
        out_secs = last_out.hour * 3600 + last_out.minute * 60
        early_min = max(0, (end_secs - out_secs) // 60)
        is_early = last_out <= early_cutoff

    gross = (late_min if is_late else 0) + (early_min if is_early else 0)

    if first_in is None or last_out is None:
        # a single punch cannot prove lateness/early leave: needs review, no auto-charge
        status = "MISSING_PUNCH"
    elif is_late and is_early:
        status = "LATE_AND_EARLY"
    elif is_late:
        status = "LATE"
    elif is_early:
        status = "EARLY_LEAVE"
    else:
        status = "PRESENT"

    if status == "MISSING_PUNCH":
        gross = 0

    return DayDecision(late_min, early_min, is_late, is_early, gross, status)


def net_deduction_minutes(gross_charged_minutes: int, approved_hourly_minutes: int) -> int:
    """Subtract approved HOURLY leave from the gross deduction so it is never double-charged."""
    return max(0, gross_charged_minutes - max(0, approved_hourly_minutes))


async def find_employee_by_biometric_id(
    db: AsyncSession, biometric_user_id: str
) -> Employee | None:
    """Direct match on employees.biometric_code."""
    return await db.scalar(
        select(Employee).where(Employee.biometric_code == biometric_user_id)
    )


async def find_employee_by_name(
    db: AsyncSession, name: str
) -> Employee | None:
    """
    Fuzzy match on full_name_spaced using norm_search:
    all normalised name words must appear in the normalised employee name.
    Returns the unique match or None.
    """
    words = norm_search(name).split()
    if not words:
        return None
    # Pull terminations are represented in employment_status; we only exclude them.
    rows = (
        await db.scalars(
            select(Employee).where(
                or_(
                    Employee.employment_status.is_(None),
                    ~Employee.employment_status.ilike("%منتهي%"),
                )
            )
        )
    ).all()
    matches = []
    for emp in rows:
        norm_emp = norm_search(emp.full_name_spaced or "")
        if all(w in norm_emp for w in words):
            matches.append(emp)
    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------------------
# DEVICE CRUD
# ---------------------------------------------------------------------------

async def list_devices(db: AsyncSession) -> list[BiometricDevice]:
    rows = await db.scalars(
        select(BiometricDevice).order_by(BiometricDevice.id)
    )
    return list(rows.all())


async def create_device(
    db: AsyncSession, actor: User, device_name: str, platform_url: str | None, org_unit_id: int | None
) -> BiometricDevice:
    device = BiometricDevice(
        device_name=device_name,
        platform_url=platform_url,
        org_unit_id=org_unit_id,
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def update_device(
    db: AsyncSession, device_id: int, **kwargs
) -> BiometricDevice:
    device = await db.get(BiometricDevice, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="الجهاز غير موجود")
    for k, v in kwargs.items():
        if v is not None:
            setattr(device, k, v)
    await db.commit()
    await db.refresh(device)
    return device


async def delete_device(db: AsyncSession, device_id: int) -> None:
    device = await db.get(BiometricDevice, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="الجهاز غير موجود")
    await db.delete(device)
    await db.commit()


# ---------------------------------------------------------------------------
# IMPORT: Excel / CSV
# ---------------------------------------------------------------------------

async def import_attendance_file(
    db: AsyncSession,
    actor: User,
    file_path: Path,
    device_id: int | None = None,
    sheet_name: str | None = None,
    header_row: int = 1,
) -> ImportOutcome:
    """
    Parse an Excel/CSV attendance sheet, resolve employees, persist AttendanceRecord
    rows (upsert on conflict), then run daily evaluation for each new/updated record.
    """
    sync_log = AttendanceSyncLog(
        device_id=device_id,
        sync_source="EXCEL_IMPORT",
    )
    db.add(sync_log)
    await db.flush()

    try:
        headers_raw, rows = read_table(file_path, sheet_name, header_row, max_rows=10000)
    except ValueError as exc:
        sync_log.error_details = str(exc)
        sync_log.finished_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=422, detail=str(exc))

    col_map = _map_headers(headers_raw)
    required = {"biometric_user_id", "attendance_date"}
    missing = required - set(col_map.values())
    if missing:
        detail = "أعمدة مطلوبة غير موجودة: " + ", ".join(missing)
        sync_log.error_details = detail
        sync_log.finished_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=422, detail=detail)

    # pre-load biometric_code -> employee mapping
    bio_cache: dict[str, Employee | None] = {}
    # pre-load name -> employee for unmapped
    name_cache: dict[str, Employee | None] = {}

    records_fetched = 0
    records_inserted = 0
    records_duplicated = 0
    unmapped: list[dict] = []
    errors: list[dict] = []
    dates_to_evaluate: set[tuple[int, date]] = set()  # (employee_id, date)

    for row_num, raw_values in rows:
        records_fetched += 1
        row: dict[str, object] = {}
        for col_idx, field in col_map.items():
            row[field] = raw_values[col_idx] if col_idx < len(raw_values) else None

        # parse required fields
        try:
            bio_id = to_ascii_digits(str(to_text(row.get("biometric_user_id")) or "").strip())
            if not bio_id:
                raise ValueError("رقم الموظف فارغ")
            att_date = to_date(row.get("attendance_date"))
            if att_date is None:
                raise ValueError("التاريخ فارغ")
        except ValueError as exc:
            errors.append({"row": row_num, "error": str(exc)})
            continue

        first_in = _parse_time(clean_cell(row.get("first_in")))
        last_out = _parse_time(clean_cell(row.get("last_out")))
        platform_status = to_text(row.get("platform_status"))
        platform_directorate = to_text(row.get("platform_directorate"))
        bio_name = to_text(row.get("biometric_employee_name"))

        # resolve employee
        if bio_id not in bio_cache:
            bio_cache[bio_id] = await find_employee_by_biometric_id(db, bio_id)
        employee: Employee | None = bio_cache[bio_id]

        if employee is None and bio_name:
            if bio_name not in name_cache:
                name_cache[bio_name] = await find_employee_by_name(db, bio_name)
            employee = name_cache[bio_name]
            if employee is not None:
                bio_cache[bio_id] = employee

        # check for existing record (upsert logic)
        existing = await db.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.biometric_user_id == bio_id,
                AttendanceRecord.attendance_date == att_date,
            )
        )

        if existing is not None:
            records_duplicated += 1
            # update platform fields in case the file has corrections
            existing.biometric_employee_name = bio_name
            existing.first_in = first_in
            existing.last_out = last_out
            existing.platform_status = platform_status
            existing.platform_directorate = platform_directorate
            if employee is not None and existing.employee_id is None:
                existing.employee_id = employee.id
            rec = existing
        else:
            rec = AttendanceRecord(
                biometric_user_id=bio_id,
                biometric_employee_name=bio_name,
                attendance_date=att_date,
                first_in=first_in,
                last_out=last_out,
                platform_status=platform_status,
                platform_directorate=platform_directorate,
                employee_id=employee.id if employee else None,
                source_type="EXCEL_IMPORT",
                import_job_id=None,
            )
            db.add(rec)
            records_inserted += 1

        await db.flush()

        if employee is None:
            unmapped.append({
                "row": row_num,
                "biometric_user_id": bio_id,
                "biometric_employee_name": bio_name,
            })
            rec.final_system_status = "UNMAPPED_USER"
        else:
            dates_to_evaluate.add((employee.id, att_date))

    sync_log.records_fetched = records_fetched
    sync_log.records_inserted = records_inserted
    sync_log.records_duplicated = records_duplicated
    sync_log.unmapped_users_count = len(unmapped)
    sync_log.finished_at = datetime.now(timezone.utc)

    if device_id:
        device = await db.get(BiometricDevice, device_id)
        if device:
            device.last_sync_at = sync_log.finished_at
            device.last_sync_status = "OK" if not errors else "PARTIAL"

    await db.commit()

    # evaluate attendance for every resolved (employee, date) pair
    for emp_id, att_date in dates_to_evaluate:
        await evaluate_attendance(db, emp_id, att_date)

    return ImportOutcome(sync_log, unmapped, errors)


# ---------------------------------------------------------------------------
# DAILY EVALUATION ENGINE
# ---------------------------------------------------------------------------

LATE_CUTOFF = time(8, 20)
EARLY_LEAVE_CUTOFF_SHORT = time(14, 40)   # standard short day


async def _is_holiday(db: AsyncSession, d: date) -> bool:
    return bool(
        await db.scalar(
            select(PublicHoliday.id).where(PublicHoliday.holiday_date == d)
        )
    )


async def _approved_full_day_leave(
    db: AsyncSession, employee_id: int, d: date
) -> LeaveRequest | None:
    """Return an approved full-day leave (not HOURLY) covering date d, if any."""
    leave_type_subq = (
        select(LeaveType.id)
        .where(LeaveType.code != "HOURLY")
        .scalar_subquery()
    )
    return await db.scalar(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == "APPROVED",
            LeaveRequest.leave_type_id.in_(leave_type_subq),
            LeaveRequest.start_date <= d,
            LeaveRequest.end_date >= d,
        )
    )


async def _approved_hourly_leave_minutes(
    db: AsyncSession, employee_id: int, d: date
) -> int:
    """Return total approved HOURLY leave minutes for the employee on date d."""
    hourly_type = await db.scalar(
        select(LeaveType.id).where(LeaveType.code == "HOURLY")
    )
    if hourly_type is None:
        return 0
    rows = (
        await db.scalars(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == "APPROVED",
                LeaveRequest.leave_type_id == hourly_type,
                LeaveRequest.start_date == d,
            )
        )
    ).all()
    return sum(r.duration_minutes for r in rows)


async def _admin_leave_type(db: AsyncSession) -> LeaveType | None:
    return await db.scalar(select(LeaveType).where(LeaveType.code == "ADMIN"))


async def evaluate_attendance(
    db: AsyncSession, employee_id: int, att_date: date
) -> AttendanceRecord | None:
    """
    Core deduction engine for one (employee, date):

    1. Weekend or public holiday → 0 deduction, status set.
    2. Approved full-day MISSION/LEAVE → 0 deduction, link leave request.
    3. Compute raw late_minutes and early_leave_minutes from first_in/last_out
       against the active WorkSchedule cutoffs.
    4. Subtract approved HOURLY leave on the same day (avoid double deduction).
    5. If net charged minutes > 0, write / update a BIOMETRIC_DEDUCT transaction
       in leave_transactions (against ADMIN leave balance).
    6. If a previous BIOMETRIC_DEDUCT exists and new net is 0, remove it.
    """
    rec = await db.scalar(
        select(AttendanceRecord)
        .where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date == att_date,
        )
        .with_for_update()
    )
    if rec is None:
        return None

    employee = await db.get(Employee, employee_id)
    if employee is None:
        return rec

    # ---- weekend ----
    if att_date.weekday() in _WEEKEND_DAYS:
        rec.final_system_status = "WEEKEND"
        rec.late_minutes = 0
        rec.early_leave_minutes = 0
        rec.is_late_beyond_cutoff = False
        rec.is_early_leave_beyond_cutoff = False
        rec.hourly_leave_minutes_charged = 0
        rec.counted_as_hourly_leave = False
        await _remove_biometric_deduct(db, rec.id)
        await db.commit()
        return rec

    # ---- public holiday ----
    if await _is_holiday(db, att_date):
        rec.final_system_status = "OFFICIAL_HOLIDAY"
        rec.late_minutes = 0
        rec.early_leave_minutes = 0
        rec.is_late_beyond_cutoff = False
        rec.is_early_leave_beyond_cutoff = False
        rec.hourly_leave_minutes_charged = 0
        rec.counted_as_hourly_leave = False
        await _remove_biometric_deduct(db, rec.id)
        await db.commit()
        return rec

    # ---- approved full-day leave ----
    full_day = await _approved_full_day_leave(db, employee_id, att_date)
    if full_day is not None:
        # Determine mission vs leave
        lt = await db.get(LeaveType, full_day.leave_type_id)
        status = "ON_MISSION" if (lt and lt.code == "MISSION") else "ON_LEAVE"
        rec.final_system_status = status
        rec.linked_leave_request_id = full_day.id
        rec.late_minutes = 0
        rec.early_leave_minutes = 0
        rec.is_late_beyond_cutoff = False
        rec.is_early_leave_beyond_cutoff = False
        rec.hourly_leave_minutes_charged = 0
        rec.counted_as_hourly_leave = False
        await _remove_biometric_deduct(db, rec.id)
        await db.commit()
        return rec

    # ---- active work schedule ----
    schedule = await schedule_on(db, att_date)
    if schedule is not None:
        official_start = schedule.official_start_time
        official_end = schedule.official_end_time
        late_cutoff = schedule.late_cutoff_time
        early_cutoff = schedule.early_leave_cutoff_time
    else:
        official_start = time(8, 0)
        official_end = time(15, 0)
        late_cutoff = LATE_CUTOFF
        early_cutoff = EARLY_LEAVE_CUTOFF_SHORT

    decision = compute_day(
        rec.first_in, rec.last_out, official_start, official_end, late_cutoff, early_cutoff
    )

    rec.late_minutes = decision.late_minutes
    rec.early_leave_minutes = decision.early_leave_minutes
    rec.is_late_beyond_cutoff = decision.is_late_beyond_cutoff
    rec.is_early_leave_beyond_cutoff = decision.is_early_leave_beyond_cutoff

    gross_charged = decision.gross_charged_minutes

    if gross_charged == 0:
        rec.hourly_leave_minutes_charged = 0
        rec.counted_as_hourly_leave = False
        rec.final_system_status = decision.status
        await _remove_biometric_deduct(db, rec.id)
        await db.commit()
        return rec

    # ---- subtract approved HOURLY leave to avoid double deduction ----
    hourly_approved = await _approved_hourly_leave_minutes(db, employee_id, att_date)
    net_charged = net_deduction_minutes(gross_charged, hourly_approved)
    rec.hourly_leave_minutes_charged = min(gross_charged, hourly_approved)
    rec.counted_as_hourly_leave = hourly_approved > 0
    rec.final_system_status = decision.status

    if net_charged == 0:
        await _remove_biometric_deduct(db, rec.id)
        await db.commit()
        return rec

    # ---- write / update BIOMETRIC_DEDUCT transaction ----
    await _upsert_biometric_deduct(db, rec, employee_id, att_date, net_charged)
    await db.commit()
    return rec


async def _remove_biometric_deduct(db: AsyncSession, att_record_id: int) -> None:
    """Remove an existing BIOMETRIC_DEDUCT transaction linked to this record, if any."""
    tx = await db.scalar(
        select(LeaveTransaction).where(
            LeaveTransaction.attendance_record_id == att_record_id,
            LeaveTransaction.transaction_type == "BIOMETRIC_DEDUCT",
        ).with_for_update()
    )
    if tx is None:
        return
    # reverse balance used_minutes
    balance = await db.scalar(
        select(LeaveBalance)
        .where(LeaveBalance.id == tx.balance_id)
        .with_for_update()
    )
    if balance is not None:
        balance.used_minutes = max(0, balance.used_minutes + tx.delta_minutes)
    await db.delete(tx)


async def _upsert_biometric_deduct(
    db: AsyncSession,
    rec: AttendanceRecord,
    employee_id: int,
    att_date: date,
    net_charged: int,
) -> None:
    """Create or update the BIOMETRIC_DEDUCT transaction and adjust LeaveBalance."""
    year = att_date.year
    admin_type = await _admin_leave_type(db)
    if admin_type is None:
        return  # no admin leave type configured; skip silently

    balance = await db.scalar(
        select(LeaveBalance)
        .where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == admin_type.id,
            LeaveBalance.year == year,
        )
        .with_for_update()
    )
    if balance is None:
        return  # no balance for this year; skip

    existing_tx = await db.scalar(
        select(LeaveTransaction).where(
            LeaveTransaction.attendance_record_id == rec.id,
            LeaveTransaction.transaction_type == "BIOMETRIC_DEDUCT",
        ).with_for_update()
    )

    if existing_tx is not None:
        # reverse old delta, then apply new
        old_delta = existing_tx.delta_minutes  # negative
        balance.used_minutes = max(0, balance.used_minutes + old_delta)
        existing_tx.delta_minutes = -net_charged
        balance.used_minutes += net_charged
    else:
        db.add(
            LeaveTransaction(
                balance_id=balance.id,
                leave_request_id=None,
                attendance_record_id=rec.id,
                transaction_type="BIOMETRIC_DEDUCT",
                delta_minutes=-net_charged,
                notes=f"خصم بصمة بتاريخ {att_date.isoformat()}",
            )
        )
        balance.used_minutes += net_charged


# ---------------------------------------------------------------------------
# BATCH RE-EVALUATE
# ---------------------------------------------------------------------------

async def re_evaluate_range(
    db: AsyncSession, date_from: date, date_to: date, employee_id: int | None = None
) -> dict:
    """Re-run evaluation for all records in a date range (optionally for one employee)."""
    q = select(AttendanceRecord).where(
        AttendanceRecord.attendance_date >= date_from,
        AttendanceRecord.attendance_date <= date_to,
        AttendanceRecord.employee_id.isnot(None),
    )
    if employee_id is not None:
        q = q.where(AttendanceRecord.employee_id == employee_id)

    recs = (await db.scalars(q)).all()
    evaluated = 0
    for rec in recs:
        await evaluate_attendance(db, rec.employee_id, rec.attendance_date)
        evaluated += 1
    return {"evaluated": evaluated}


# ---------------------------------------------------------------------------
# QUERIES
# ---------------------------------------------------------------------------

async def list_records(
    db: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    employee_id: int | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[AttendanceRecord]:
    q = select(AttendanceRecord).order_by(
        AttendanceRecord.attendance_date.desc(), AttendanceRecord.id
    )
    if date_from:
        q = q.where(AttendanceRecord.attendance_date >= date_from)
    if date_to:
        q = q.where(AttendanceRecord.attendance_date <= date_to)
    if employee_id:
        q = q.where(AttendanceRecord.employee_id == employee_id)
    if status:
        q = q.where(AttendanceRecord.final_system_status == status)
    q = q.limit(limit).offset(offset)
    return list((await db.scalars(q)).all())


async def get_record(db: AsyncSession, record_id: int) -> AttendanceRecord:
    rec = await db.get(AttendanceRecord, record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="سجل الحضور غير موجود")
    return rec


async def review_record(
    db: AsyncSession,
    actor: User,
    record_id: int,
    final_system_status: str,
    review_notes: str | None,
) -> AttendanceRecord:
    rec = await db.scalar(
        select(AttendanceRecord)
        .where(AttendanceRecord.id == record_id)
        .with_for_update()
    )
    if rec is None:
        raise HTTPException(status_code=404, detail="سجل الحضور غير موجود")
    rec.final_system_status = final_system_status
    rec.review_notes = review_notes
    rec.reviewed_by_user_id = actor.id
    rec.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(rec)
    return rec
