import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import User
from app.models.attendance import AttendanceSyncLog
from app.schemas.attendance import (
    AttendanceImportResult,
    AttendanceRecordRead,
    AttendanceReEvaluateResult,
    AttendanceReview,
    AttendanceSyncLogRead,
    BiometricDeviceCreate,
    BiometricDeviceRead,
    BiometricDeviceUpdate,
)
from app.services import attendance as svc

router = APIRouter(prefix="/attendance", tags=["attendance"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")
admin_only = require_roles("CENTRAL_ADMIN", "CENTRAL_HR")


# ---------------------------------------------------------------------------
# BIOMETRIC DEVICES
# ---------------------------------------------------------------------------

@router.get("/devices", response_model=list[BiometricDeviceRead])
async def list_devices(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(hr_or_admin),
):
    return await svc.list_devices(db)


@router.post("/devices", response_model=BiometricDeviceRead, status_code=201)
async def create_device(
    data: BiometricDeviceCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_only),
):
    return await svc.create_device(
        db, actor, data.device_name, data.platform_url, data.org_unit_id
    )


@router.patch("/devices/{device_id}", response_model=BiometricDeviceRead)
async def update_device(
    device_id: int,
    data: BiometricDeviceUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_only),
):
    return await svc.update_device(
        db,
        device_id,
        **{k: v for k, v in data.model_dump(exclude_none=True).items()},
    )


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_only),
):
    await svc.delete_device(db, device_id)


# ---------------------------------------------------------------------------
# IMPORT
# ---------------------------------------------------------------------------

@router.post("/import", response_model=AttendanceImportResult, status_code=201)
async def import_file(
    file: UploadFile = File(...),
    device_id: int | None = Form(default=None),
    sheet_name: str | None = Form(default=None),
    header_row: int = Form(default=1),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    suffix = Path(file.filename or "data.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".csv"}:
        raise HTTPException(status_code=422, detail="نوع الملف غير مدعوم، استخدم xlsx أو csv")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        outcome = await svc.import_attendance_file(
            db, actor, tmp_path, device_id, sheet_name, header_row
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    log = outcome.sync_log
    return AttendanceImportResult(
        import_job_id=log.id,
        records_fetched=log.records_fetched,
        records_inserted=log.records_inserted,
        records_duplicated=log.records_duplicated,
        unmapped_users=outcome.unmapped,
        errors=outcome.errors,
    )


# ---------------------------------------------------------------------------
# RECORDS
# ---------------------------------------------------------------------------

@router.get("/records", response_model=list[AttendanceRecordRead])
async def list_records(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    employee_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(hr_or_admin),
):
    return await svc.list_records(db, date_from, date_to, employee_id, status, limit, offset)


@router.get("/records/{record_id}", response_model=AttendanceRecordRead)
async def get_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(hr_or_admin),
):
    return await svc.get_record(db, record_id)


@router.post("/records/{record_id}/review", response_model=AttendanceRecordRead)
async def review_record(
    record_id: int,
    data: AttendanceReview,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.review_record(
        db, actor, record_id, data.final_system_status, data.review_notes
    )


@router.post("/records/{record_id}/re-evaluate", response_model=AttendanceRecordRead)
async def re_evaluate_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(hr_or_admin),
):
    rec = await svc.get_record(db, record_id)
    if rec.employee_id is None:
        raise HTTPException(status_code=422, detail="السجل غير مرتبط بموظف")
    return await svc.evaluate_attendance(db, rec.employee_id, rec.attendance_date)


# ---------------------------------------------------------------------------
# BATCH RE-EVALUATE
# ---------------------------------------------------------------------------

@router.post("/re-evaluate", response_model=AttendanceReEvaluateResult)
async def re_evaluate_range(
    date_from: date = Query(...),
    date_to: date = Query(...),
    employee_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_only),
):
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="تاريخ النهاية قبل تاريخ البداية")
    result = await svc.re_evaluate_range(db, date_from, date_to, employee_id)
    return AttendanceReEvaluateResult(**result)


# ---------------------------------------------------------------------------
# SYNC LOGS
# ---------------------------------------------------------------------------

@router.get("/sync-logs", response_model=list[AttendanceSyncLogRead])
async def list_sync_logs(
    device_id: int | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(hr_or_admin),
):
    q = select(AttendanceSyncLog).order_by(AttendanceSyncLog.id.desc()).limit(limit)
    if device_id:
        q = q.where(AttendanceSyncLog.device_id == device_id)
    rows = await db.scalars(q)
    return rows.all()
