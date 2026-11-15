from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles, get_current_user
from app.core.database import get_db
from app.core.labels_ar import (
    ACTION_LABELS_AR,
    ASSIGNMENT_ACTION_LABELS_AR,
    ENTRY_SOURCE_LABELS_AR,
    IMPORT_ERROR_TYPE_LABELS_AR,
    IMPORT_STATUS_LABELS_AR,
    STATUS_LABELS_AR,
    TRANSACTION_LABELS_AR,
)
from app.models import AppointmentCategory, Employee, Governorate, User, LeaveType
from app.services.scope import get_scope

router = APIRouter(prefix="/lookups", tags=["lookups"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")


class CategoryRead(BaseModel):
    code: str
    label_ar: str
    employment_type: str


class GovernorateRead(BaseModel):
    code: str
    name_ar: str
    name_en: str


@router.get("/appointment-categories", response_model=list[CategoryRead])
async def appointment_categories(
    employment_type: str | None = Query(None, description="مثبت أو متعاقد"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(hr_or_admin),
):
    stmt = select(AppointmentCategory).order_by(AppointmentCategory.id)
    if employment_type:
        stmt = stmt.where(AppointmentCategory.employment_type == employment_type)
    rows = (await db.scalars(stmt)).all()
    return [
        CategoryRead(
            code=c.category_code,
            label_ar=c.category_label_ar,
            employment_type=c.employment_type,
        )
        for c in rows
    ]


@router.get("/governorates", response_model=list[GovernorateRead])
async def governorates(
    db: AsyncSession = Depends(get_db), _: User = Depends(hr_or_admin)
):
    rows = (await db.scalars(select(Governorate).order_by(Governorate.id))).all()
    return [
        GovernorateRead(
            code=g.governorate_code,
            name_ar=g.governorate_name_ar,
            name_en=g.governorate_name_en,
        )
        for g in rows
    ]

class LeaveTypeRead(BaseModel):
    code: str
    name_ar: str
    allow_employee_request: bool
    deducts_balance: bool
    min_duration_minutes: int | None
    max_duration_minutes: int | None
    enforce_72h_rule: bool


@router.get("/leave-types", response_model=list[LeaveTypeRead])
async def leave_types(
    db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)
):
    rows = await db.scalars(
        select(LeaveType).where(LeaveType.is_active).order_by(LeaveType.id)
    )
    return [
        LeaveTypeRead(
            code=t.code,
            name_ar=t.name_ar,
            allow_employee_request=t.allow_employee_request,
            deducts_balance=t.deducts_balance,
            min_duration_minutes=t.min_duration_minutes,
            max_duration_minutes=t.max_duration_minutes,
            enforce_72h_rule=t.enforce_72h_rule,
        )
        for t in rows.all()
    ]


# ---------------------------------------------------------------- labels
LABEL_MAPPINGS: dict[str, dict[str, str]] = {
    "leave_status": STATUS_LABELS_AR,
    "leave_action": ACTION_LABELS_AR,
    "leave_transaction": TRANSACTION_LABELS_AR,
    "entry_source": ENTRY_SOURCE_LABELS_AR,
    "import_status": IMPORT_STATUS_LABELS_AR,
    "import_error_type": IMPORT_ERROR_TYPE_LABELS_AR,
    "assignment_action": ASSIGNMENT_ACTION_LABELS_AR,
}


class LabelItem(BaseModel):
    code: str
    label_ar: str


@router.get("/labels", response_model=dict[str, list[LabelItem]])
async def labels(
    group: str | None = Query(None, description="اسم مجموعة التسميات، أو احذفه لإرجاع الكل"),
    _: User = Depends(get_current_user),
):
    """يرجع خريطة المجموعة -> [{code, label_ar}].
    مثال: /lookups/labels?group=leave_status
    """
    groups = {group: LABEL_MAPPINGS[group]} if group else LABEL_MAPPINGS
    if group and group not in LABEL_MAPPINGS:
        raise HTTPException(
            status_code=422, detail=f"مجموعة تسميات غير معروفة: {group}"
        )
    return {
        g: [LabelItem(code=k, label_ar=v) for k, v in mapping.items()]
        for g, mapping in groups.items()
    }


# قائمة بيضاء لقيم الحقول القابلة للاستخراج من جدول الموظفين
_EMPLOYEE_FIELD_WHITELIST = {
    "permanent_or_contract",
    "employment_status",
    "job_title_name",
    "job_classification",
    "current_job_category",
    "job_rank",
    "job_grade",
    "marital_status",
    "country",
    "civil_reg_governorate",
    "residence_governorate",
    "appointment_category_code",
    "governorate_code",
}


@router.get("/employee-field-values/{field}", response_model=list[LabelItem])
async def employee_field_values(
    field: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    """قيم مميزة لحقل ما في جدول الموظفين ضمن نطاق صلاحية المستخدم.
    يعيد [{code, label_ar}] حيث code = القيمة نفسها و label_ar = القيمة.
    مفيد لتعبئة قوائم منسدلة من بيانات موجودة فعلاً.
    """
    if field not in _EMPLOYEE_FIELD_WHITELIST:
        raise HTTPException(
            status_code=422,
            detail=f"حقل غير مسموح استخراج قيمه: {field}",
        )
    col = getattr(Employee, field, None)
    if col is None:
        raise HTTPException(status_code=422, detail="الحقل غير موجود")
    scope = await get_scope(db, actor)
    stmt = select(col).where(col.is_not(None)).distinct().order_by(col)
    if scope is not None:
        stmt = stmt.where(scope.employee_filter())
    rows = (await db.execute(stmt)).scalars().all()
    return [LabelItem(code=str(v), label_ar=str(v)) for v in rows]