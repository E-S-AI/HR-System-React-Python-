from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, EmployeeChangeLog, User
from app.services.scope import get_scope


async def locked_employee(db: AsyncSession, actor: User, employee_id: int) -> Employee:
    """يقفل صف الموظف (يسلسل التعديلات المتزامنة) ويطبق نطاق الصلاحية (404 خارجه)."""
    emp = await db.scalar(
        select(Employee).where(Employee.id == employee_id).with_for_update()
    )
    scope = await get_scope(db, actor)
    if emp is None or (
        scope is not None and not scope.allows(emp.governorate_code, emp.org_unit_id)
    ):
        raise HTTPException(status_code=404, detail="الموظف غير موجود")
    return emp


def add_log(db, employee_id, actor_id, field, old, new, reason=None) -> None:
    db.add(
        EmployeeChangeLog(
            employee_id=employee_id,
            changed_by_user_id=actor_id,
            field_name=field,
            old_value=old,
            new_value=new,
            change_reason=reason,
        )
    )