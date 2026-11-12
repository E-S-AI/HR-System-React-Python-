from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models import User
from app.schemas.leave_form import LeaveFormRead, LeaveFormUploadItem
from app.services import leave_form_templates as svc

router = APIRouter(prefix="/leave-forms", tags=["leave-forms"])

central_hr = require_roles("CENTRAL_ADMIN", "CENTRAL_HR")


@router.post("", response_model=list[LeaveFormUploadItem], status_code=201)
async def upload_templates(
    file: UploadFile = File(..., description="ملف PDF يحوي النماذج الورقية"),
    page_map: str | None = Form(
        None, description="مثال: HOURLY=1,ADMIN=2,MISSION=3,UNPAID=4"
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(central_hr),
):
    """رفع ملف النماذج الورقية وتقسيمه إلى صفحة لكل نوع إجازة."""
    content = await file.read(svc.MAX_TEMPLATE_BYTES + 1)
    return await svc.upload_templates(db, content, page_map)


@router.get("", response_model=list[LeaveFormRead])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await svc.list_templates(db)


@router.get("/{leave_type_code}")
async def download_template(
    leave_type_code: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """تحميل النموذج الورقي: يطبعه الموظف ويوقّعه ثم يرفعه عبر POST /leave-requests/{id}/paper."""
    path = await svc.get_template_path(db, leave_type_code)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"leave_form_{leave_type_code.upper()}.pdf",
    )


@router.delete("/{leave_type_code}", status_code=204)
async def delete_template(
    leave_type_code: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(central_hr),
):
    await svc.delete_template(db, leave_type_code)
    return Response(status_code=204)
