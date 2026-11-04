import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import ImportJob, User
from app.schemas.imports import ImportErrorRead, ImportJobRead, ImportPreview
from app.services import imports as svc
from app.services.employee_import import build_template
from app.services.users import is_admin
from app.services.employee_import import build_template, build_template_csv

router = APIRouter(prefix="/imports", tags=["imports"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/employees/template")
async def employees_template(
    format: Literal["xlsx", "csv"] = "xlsx", _: User = Depends(hr_or_admin)
):
    if format == "csv":
        return Response(
            content=build_template_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="employees_template.csv"'},
        )
    return _xlsx(await asyncio.to_thread(build_template), "employees_template.xlsx")



@router.post("/employees", response_model=ImportPreview, status_code=201)
async def upload_employees(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(None),
    header_row: int = Form(1, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    content = await file.read(svc.MAX_BYTES + 1)
    job = await svc.create_preview(
        db, actor, content, file.filename or "upload.xlsx", sheet_name or None, header_row
    )
    errors = await svc.list_errors(db, job.id, 0, 20)
    data = ImportJobRead.model_validate(job).model_dump()
    return ImportPreview(
        **data, sample_errors=[ImportErrorRead.model_validate(e) for e in errors]
    )


@router.get("", response_model=list[ImportJobRead])
async def list_jobs(
    db: AsyncSession = Depends(get_db), actor: User = Depends(hr_or_admin)
):
    stmt = select(ImportJob).order_by(ImportJob.id.desc()).limit(50)
    if not is_admin(actor):
        stmt = stmt.where(ImportJob.created_by_user_id == actor.id)
    return (await db.scalars(stmt)).all()


@router.get("/{job_id}", response_model=ImportJobRead)
async def get_job(
    job_id: int, db: AsyncSession = Depends(get_db), actor: User = Depends(hr_or_admin)
):
    return await svc.get_job(db, actor, job_id)


@router.get("/{job_id}/errors", response_model=list[ImportErrorRead])
async def job_errors(
    job_id: int,
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    await svc.get_job(db, actor, job_id)
    return await svc.list_errors(db, job_id, skip, limit)


@router.get("/{job_id}/errors.xlsx")
async def job_errors_file(
    job_id: int, db: AsyncSession = Depends(get_db), actor: User = Depends(hr_or_admin)
):
    data = await svc.build_error_file(db, actor, job_id)
    return _xlsx(data, f"import_{job_id}_errors.xlsx")


@router.post("/{job_id}/commit", response_model=ImportJobRead)
async def commit(
    job_id: int, db: AsyncSession = Depends(get_db), actor: User = Depends(hr_or_admin)
):
    return await svc.commit_import(db, actor, job_id)