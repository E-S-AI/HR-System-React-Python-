from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import User
from app.schemas.employee import (
    AccountResult,
    CategoryAssign,
    ChangeLogRead,
    EmployeeCreate,
    EmployeeCreated,
    EmployeeDetail,
    EmployeePatch,
    EmployeePatchResult,
    EmployeeRead,
)
from app.schemas.exports import EmployeeExportFilters
from app.services import employees as svc

router = APIRouter(prefix="/employees", tags=["employees"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")


@router.post("", response_model=EmployeeCreated, status_code=201)
async def create(
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    employee, extras = await svc.create_employee(db, data, actor)
    return EmployeeCreated(
        employee=await svc.build_detail(db, employee),
        account=AccountResult(**extras["account"]) if extras["account"] else None,
        balance_granted=extras["balance_granted"],
        warnings=extras["warnings"],
    )


@router.get("", response_model=list[EmployeeRead])
async def list_employees(
    skip: int = 0,
    limit: int = Query(50, le=200),
    search: str | None = None,
    governorate_code: str | None = None,
    org_unit_id: int | None = None,
    permanent_or_contract: str | None = None,
    employment_status: str | None = None,
    has_account: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    filters = EmployeeExportFilters(
        search=search,
        governorate_code=governorate_code,
        org_unit_id=org_unit_id,
        permanent_or_contract=permanent_or_contract,
        employment_status=employment_status,
        has_account=has_account,
    )
    return await svc.list_employees(db, actor, filters, skip, limit)


@router.get("/{employee_id}", response_model=EmployeeDetail)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.get_detail(db, actor, employee_id)


@router.patch("/{employee_id}", response_model=EmployeePatchResult)
async def update_employee(
    employee_id: int,
    data: EmployeePatch,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    emp, changed, recalculated, deactivated = await svc.patch_employee(
        db, actor, employee_id, data
    )
    return EmployeePatchResult(
        employee=await svc.build_detail(db, emp),
        changed_fields=changed,
        balances_recalculated=recalculated,
        account_deactivated=deactivated,
    )


@router.get("/{employee_id}/changes", response_model=list[ChangeLogRead])
async def employee_changes(
    employee_id: int,
    skip: int = 0,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await svc.list_changes(db, actor, employee_id, skip, limit)


@router.post("/{employee_id}/appointment-category", response_model=EmployeeDetail)
async def set_appointment_category(
    employee_id: int,
    data: CategoryAssign,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    emp = await svc.assign_category(db, actor, employee_id, data.category_code)
    return await svc.build_detail(db, emp)