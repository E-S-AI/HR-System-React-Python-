from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import ExportLog, User
from app.schemas.exports import EmployeeExportRequest, ExportColumnRead, ExportLogRead
from app.services.employee_export import (
    EXPORT_COLUMNS,
    export_employees,
    export_filename,
)

router = APIRouter(prefix="/exports", tags=["exports"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")
admin_only = require_roles("CENTRAL_ADMIN")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/employees/columns", response_model=list[ExportColumnRead])
async def employee_columns(_: User = Depends(hr_or_admin)):
    return [
        ExportColumnRead(key=c.key, label=c.label, default=c.default)
        for c in EXPORT_COLUMNS
    ]


@router.post("/employees")
async def export_employees_file(
    data: EmployeeExportRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    content = await export_employees(db, actor, data.filters, data.columns)
    return Response(
        content=content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{export_filename()}"'},
    )


@router.get("/logs", response_model=list[ExportLogRead])
async def export_logs(
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_only),
):
    rows = await db.scalars(select(ExportLog).order_by(ExportLog.id.desc()).limit(limit))
    return rows.all()