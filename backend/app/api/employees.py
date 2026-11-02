from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Employee
from app.schemas.employee import EmployeeCreate, EmployeeRead
from app.services.employees import create_employee

router = APIRouter(prefix="/employees", tags=["employees"])


@router.post("", response_model=EmployeeRead, status_code=201)
async def create(data: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    return await create_employee(db, data)


@router.get("", response_model=list[EmployeeRead])
async def list_employees(
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.scalars(
        select(Employee).order_by(Employee.id).offset(skip).limit(limit)
    )
    return rows.all()


@router.get("/{employee_id}", response_model=EmployeeRead)
async def get_employee(employee_id: int, db: AsyncSession = Depends(get_db)):
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    return employee