from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppointmentCategory, Employee, Governorate, OrgUnit, User
from app.schemas.employee import EmployeeCreate
from app.services.scope import get_scope

UNIQUE_MESSAGES = {
    "national_id": "الرقم الوطني مسجل مسبقاً لموظف آخر",
    "biometric_code": "رقم البصمة مسجل مسبقاً لموظف آخر",
    "employee_code": "كود الموظف مكرر",
}


async def create_employee(
    db: AsyncSession, data: EmployeeCreate, actor: User
) -> Employee:
    scope = await get_scope(db, actor)
    if scope is not None and not scope.allows(data.governorate_code, data.org_unit_id):
        raise HTTPException(
            status_code=403, detail="هذه المحافظة أو الوحدة خارج نطاق صلاحيتك"
        )

    governorate = await db.scalar(
        select(Governorate).where(Governorate.governorate_code == data.governorate_code)
    )
    if governorate is None:
        raise HTTPException(status_code=422, detail="رمز المحافظة غير موجود")

    if data.org_unit_id is not None and await db.get(OrgUnit, data.org_unit_id) is None:
        raise HTTPException(status_code=422, detail="الوحدة التنظيمية غير موجودة")

    category = None
    if data.appointment_category_code:
        category = await db.scalar(
            select(AppointmentCategory).where(
                AppointmentCategory.category_code == data.appointment_category_code
            )
        )
        if category is None:
            raise HTTPException(status_code=422, detail="رمز فئة التعيين غير موجود")

    permanent_or_contract = data.permanent_or_contract or (
        category.employment_type if category else None
    )
    if permanent_or_contract is None:
        raise HTTPException(
            status_code=422, detail="حدد (مثبت أو متعاقد) أو اختر فئة تعيين"
        )

    serial = await db.scalar(text("select nextval('employee_global_serial_seq')"))
    formatted = f"{serial:04d}"
    code = (
        f"{governorate.governorate_code}-{category.category_code}-{formatted}"
        if category
        else None
    )
    full_name = " ".join(
        p for p in (data.first_name, data.father_name, data.last_name) if p
    )

    values = data.model_dump(exclude={"permanent_or_contract"})
    employee = Employee(
        **values,
        permanent_or_contract=permanent_or_contract,
        global_serial_number=serial,
        formatted_serial=formatted,
        employee_code=code,
        full_name_spaced=full_name,
    )
    db.add(employee)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        text_error = str(exc.orig)
        for field, message in UNIQUE_MESSAGES.items():
            if field in text_error:
                raise HTTPException(status_code=409, detail=message)
        raise HTTPException(status_code=409, detail="بيانات مكررة أو غير صالحة")

    await db.refresh(employee)
    return employee


async def assign_category(
    db: AsyncSession, actor: User, employee_id: int, category_code: str
) -> Employee:
    employee = await db.scalar(
        select(Employee).where(Employee.id == employee_id).with_for_update()
    )
    scope = await get_scope(db, actor)
    if employee is None or (
        scope is not None
        and not scope.allows(employee.governorate_code, employee.org_unit_id)
    ):
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    if employee.employee_code or employee.appointment_category_code:
        raise HTTPException(
            status_code=409, detail="كود الموظف مولّد مسبقاً وهو ثابت لا يتغير"
        )

    category = await db.scalar(
        select(AppointmentCategory).where(
            AppointmentCategory.category_code == category_code
        )
    )
    if category is None:
        raise HTTPException(status_code=422, detail="رمز فئة التعيين غير موجود")
    if category.employment_type != employee.permanent_or_contract:
        raise HTTPException(
            status_code=422,
            detail=f"الفئة {category_code} ({category.employment_type}) لا تناسب موظفاً {employee.permanent_or_contract}",
        )

    employee.appointment_category_code = category.category_code
    employee.employee_code = (
        f"{employee.governorate_code}-{category.category_code}-{employee.formatted_serial}"
    )
    employee.updated_by_hr_id = actor.id
    await db.commit()
    await db.refresh(employee)
    return employee