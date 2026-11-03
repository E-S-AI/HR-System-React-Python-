from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import Employee, User
from app.schemas.employee import EmployeeCreate, EmployeeRead
from app.services.employees import create_employee
from app.services.scope import get_scope

router = APIRouter(prefix="/employees", tags=["employees"])

hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")


@router.post("", response_model=EmployeeRead, status_code=201)
async def create(
    data: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    return await create_employee(db, data, actor)


@router.get("", response_model=list[EmployeeRead])
async def list_employees(
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    stmt = select(Employee).order_by(Employee.id).offset(skip).limit(limit)
    scope = await get_scope(db, actor)
    if scope is not None:
        stmt = stmt.where(scope.employee_filter())
    rows = await db.scalars(stmt)
    return rows.all()


@router.get("/{employee_id}", response_model=EmployeeRead)
async def get_employee(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(hr_or_admin),
):
    employee = await db.get(Employee, employee_id)
    scope = await get_scope(db, actor)
    if employee is None or (
        scope is not None
        and not scope.allows(employee.governorate_code, employee.org_unit_id)
    ):
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    return employee