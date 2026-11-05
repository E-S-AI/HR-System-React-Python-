from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models import User
from app.schemas.leave_request import (
    ApprovalLogRead,
    ApproveRequest,
    ExpireResult,
    LeaveRequestCreate,
    LeaveRequestRead,
    RejectRequest,
)
from app.services import leave_requests as svc

router = APIRouter(prefix="/leave-requests", tags=["leave-requests"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")
admin_only = require_roles("CENTRAL_ADMIN")
PAPER_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf"}


@router.post("", response_model=LeaveRequestRead, status_code=201)
async def create(
    data: LeaveRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request_id = await svc.create_request(db, user, data)
    return await svc.fetch_read(db, request_id)


@router.get("/mine", response_model=list[LeaveRequestRead])
async def my_requests(
    status: str | None = None,
    year: int | None = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.list_mine(db, user, status, year, skip, limit)


@router.get("", response_model=list[LeaveRequestRead])
async def hr_list(
    employee_id: int | None = None,
    status: str | None = None,
    leave_type_code: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.list_for_hr(
        db, actor, employee_id, status, leave_type_code, date_from, date_to, skip, limit
    )


@router.post("/maintenance/expire-overdue", response_model=ExpireResult)
async def expire_overdue(
    db: AsyncSession = Depends(get_db), _: User = Depends(admin_only)
):
    return ExpireResult(rejected=await svc.auto_reject_overdue(db))


@router.get("/{request_id}", response_model=LeaveRequestRead)
async def get_one(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await svc.get_visible(db, user, request_id)
    return await svc.fetch_read(db, request_id)


@router.get("/{request_id}/logs", response_model=list[ApprovalLogRead])
async def logs(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await svc.get_visible(db, user, request_id)
    return await svc.list_logs(db, request_id)


@router.get("/{request_id}/paper")
async def download_paper(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    req = await svc.get_visible(db, user, request_id)
    if not req.paper_attachment_path:
        raise HTTPException(status_code=404, detail="لا توجد ورقة مرفوعة")
    path = svc.paper_abs(req.paper_attachment_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="ملف الورقة غير موجود على الخادم")
    return FileResponse(
        path,
        media_type=PAPER_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        filename=f"leave_{req.id}{path.suffix}",
    )


@router.post("/{request_id}/paper", response_model=LeaveRequestRead)
async def upload_paper(
    request_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    content = await file.read(svc.MAX_PAPER_BYTES + 1)
    await svc.upload_paper(db, user, request_id, content)
    return await svc.fetch_read(db, request_id)


@router.post("/{request_id}/cancel", response_model=LeaveRequestRead)
async def cancel(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await svc.cancel_request(db, user, request_id)
    return await svc.fetch_read(db, request_id)


@router.post("/{request_id}/approve", response_model=LeaveRequestRead)
async def approve(
    request_id: int,
    data: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    await svc.hr_decide(db, actor, request_id, True, data.notes, data.decision_number)
    return await svc.fetch_read(db, request_id)


@router.post("/{request_id}/reject", response_model=LeaveRequestRead)
async def reject(
    request_id: int,
    data: RejectRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    await svc.hr_decide(db, actor, request_id, False, data.notes, None)
    return await svc.fetch_read(db, request_id)