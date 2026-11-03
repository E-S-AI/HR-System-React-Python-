import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import ImportJob, ImportJobError, User
from app.services.employee_import import analyze, insert_valid
from app.services.excel_utils import put_cell, workbook_bytes
from app.services.users import is_admin

logger = logging.getLogger(__name__)

MAX_BYTES = 10 * 1024 * 1024
MAX_ERRORS_STORED = 20_000


def job_file(job_id: int) -> Path:
    return Path(settings.upload_dir) / "imports" / f"{job_id}.xlsx"


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


async def get_job(
    db: AsyncSession, actor: User, job_id: int, lock: bool = False
) -> ImportJob:
    stmt = select(ImportJob).where(ImportJob.id == job_id)
    if lock:
        stmt = stmt.with_for_update()
    job = await db.scalar(stmt)
    if job is None or (job.created_by_user_id != actor.id and not is_admin(actor)):
        raise HTTPException(status_code=404, detail="عملية الاستيراد غير موجودة")
    return job


async def _store_errors(db: AsyncSession, job_id: int, errors: list) -> None:
    await db.execute(delete(ImportJobError).where(ImportJobError.import_job_id == job_id))
    rows = [
        {
            "import_job_id": job_id,
            "row_number": r,
            "column_name": col,
            "raw_value": raw,
            "error_type": etype,
            "error_message_ar": msg,
        }
        for (r, col, raw, etype, msg) in errors[:MAX_ERRORS_STORED]
    ]
    for i in range(0, len(rows), 1000):
        await db.execute(insert(ImportJobError), rows[i:i + 1000])


async def list_errors(
    db: AsyncSession, job_id: int, skip: int, limit: int
) -> list[ImportJobError]:
    rows = await db.scalars(
        select(ImportJobError)
        .where(ImportJobError.import_job_id == job_id)
        .order_by(ImportJobError.row_number, ImportJobError.id)
        .offset(skip)
        .limit(limit)
    )
    return list(rows.all())


async def create_preview(
    db: AsyncSession,
    actor: User,
    content: bytes,
    filename: str,
    sheet_name: str | None,
    header_row: int,
) -> ImportJob:
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="الملف يجب أن يكون بصيغة xlsx")
    if not content:
        raise HTTPException(status_code=422, detail="الملف فارغ")
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="حجم الملف يتجاوز 10 ميغابايت")

    digest = hashlib.sha256(content).hexdigest()
    done = await db.scalar(
        select(ImportJob.id).where(
            ImportJob.file_sha256 == digest,
            ImportJob.module_name == "EMPLOYEES",
            ImportJob.status == "COMMITTED",
        )
    )
    if done:
        raise HTTPException(
            status_code=409, detail=f"هذا الملف نفسه استُورد سابقاً (عملية رقم {done})"
        )

    job = ImportJob(
        module_name="EMPLOYEES",
        original_file_name=filename[:255],
        sheet_name=sheet_name,
        file_sha256=digest,
        import_mode="CREATE_ONLY",
        status="PROCESSING",
        created_by_user_id=actor.id,
    )
    db.add(job)
    await db.flush()
    job_id = job.id
    path = job_file(job_id)
    try:
        await asyncio.to_thread(_write_file, path, content)
        result = await analyze(db, path, sheet_name, header_row, actor)
        job.column_mapping = {**result.mapping_info, "header_row": header_row}
        job.total_rows = result.total_rows
        job.valid_new_rows = len(result.valid)
        job.error_rows = result.error_rows
        job.duplicate_rows = result.duplicate_rows
        job.status = "FAILED" if result.file_failed else "PREVIEW_READY"
        await _store_errors(db, job_id, result.errors)
        await db.commit()
    except Exception:
        logger.exception("import preview failed")
        await db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="تعذّرت معالجة الملف")
    await db.refresh(job)
    return job


async def commit_import(db: AsyncSession, actor: User, job_id: int) -> ImportJob:
    job = await get_job(db, actor, job_id, lock=True)
    if job.status != "PREVIEW_READY":
        await db.rollback()
        raise HTTPException(
            status_code=409, detail=f"لا يمكن اعتماد هذه العملية (حالتها: {job.status})"
        )
    path = job_file(job.id)
    if not path.exists():
        await db.rollback()
        raise HTTPException(status_code=410, detail="ملف الاستيراد غير موجود، أعد رفعه")
    content = await asyncio.to_thread(path.read_bytes)
    if hashlib.sha256(content).hexdigest() != job.file_sha256:
        await db.rollback()
        raise HTTPException(status_code=409, detail="الملف المخزن تغيّر، أعد رفعه")

    header_row = (job.column_mapping or {}).get("header_row", 1)
    try:
        # نعيد التحليل لنكتشف أي تكرار حدث بعد المعاينة
        result = await analyze(db, path, job.sheet_name, header_row, actor)
        if result.file_failed or not result.valid:
            await db.rollback()
            raise HTTPException(status_code=422, detail="لا توجد صفوف صالحة للاعتماد")
        await insert_valid(db, result.valid, actor.id)
        job.total_rows = result.total_rows
        job.valid_new_rows = len(result.valid)
        job.error_rows = result.error_rows
        job.duplicate_rows = result.duplicate_rows
        job.status = "COMMITTED"
        job.committed_at = datetime.now(timezone.utc)
        await _store_errors(db, job.id, result.errors)
        await db.commit()
    except HTTPException:
        raise
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="تعارض أثناء الحفظ (ربما أُضيف موظف مطابق بالتزامن). لم يُحفظ شيء، أعد المعاينة",
        )
    except Exception:
        logger.exception("import commit failed")
        await db.rollback()
        raise HTTPException(status_code=500, detail="تعذّر اعتماد الاستيراد، لم يُحفظ شيء")
    await db.refresh(job)
    return job


def _error_workbook(path: Path, sheet_name, header_row: int, by_row: dict) -> bytes:
    src = load_workbook(path, read_only=True, data_only=True)
    try:
        ws_src = src[sheet_name] if sheet_name else src.worksheets[0]
        ws_src.reset_dimensions()
        wb = Workbook()
        ws = wb.active
        ws.title = "الأخطاء"
        ws.sheet_view.rightToLeft = True
        out = 1
        for idx, row in enumerate(ws_src.iter_rows(values_only=True), start=1):
            if idx == header_row:
                vals = list(row) + ["أخطاء الصف (يُتجاهل عند إعادة الرفع)"]
            elif idx in by_row:
                vals = list(row) + [" | ".join(by_row[idx])]
            else:
                continue
            for c, v in enumerate(vals, start=1):
                put_cell(ws, out, c, v)
            out += 1
        return workbook_bytes(wb)
    finally:
        src.close()


async def build_error_file(db: AsyncSession, actor: User, job_id: int) -> bytes:
    job = await get_job(db, actor, job_id)
    rows = (
        await db.execute(
            select(
                ImportJobError.row_number,
                ImportJobError.column_name,
                ImportJobError.error_message_ar,
            )
            .where(ImportJobError.import_job_id == job.id)
            .order_by(ImportJobError.row_number)
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="لا توجد أخطاء في هذه العملية")
    by_row: dict[int, list[str]] = {}
    for r, col, msg in rows:
        by_row.setdefault(r, []).append(f"{col}: {msg}" if col else msg)
    path = job_file(job.id)
    if not path.exists():
        raise HTTPException(status_code=410, detail="ملف الاستيراد الأصلي غير موجود")
    header_row = (job.column_mapping or {}).get("header_row", 1)
    return await asyncio.to_thread(_error_workbook, path, job.sheet_name, header_row, by_row)