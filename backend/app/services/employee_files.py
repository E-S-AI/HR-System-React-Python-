from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmployeeQualification, EmployeeTraining, User
from app.schemas.employee import QualificationIn, TrainingIn
from app.schemas.employee_files import QualificationPatch, TrainingPatch
from app.services.employee_helpers import add_log, locked_employee
from app.services.leave_balances import visible_employee


def _q_summary(q: EmployeeQualification) -> str:
    return (
        f"#{q.id} {q.qualification_level} | {q.specialization or '-'} | "
        f"{q.issuing_institution or '-'} | {q.graduation_year or '-'} | "
        f"مؤهل التعيين: {'نعم' if q.is_hiring_qualification else 'لا'}"
    )


def _t_summary(t: EmployeeTraining) -> str:
    return (
        f"#{t.id} {t.course_name} | {t.training_provider or '-'} | "
        f"{t.course_date or '-'} | {t.duration_text or '-'}"
    )


def _bad(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


# ------------------------------------------------------------------ المؤهلات
async def list_qualifications(db: AsyncSession, actor: User, employee_id: int):
    await visible_employee(db, actor, employee_id)
    rows = await db.scalars(
        select(EmployeeQualification)
        .where(EmployeeQualification.employee_id == employee_id)
        .order_by(EmployeeQualification.id)
    )
    return list(rows.all())


async def _clear_hiring(db: AsyncSession, employee_id: int, keep_id: int | None) -> None:
    """يُلغي مؤهل التعيين الحالي قبل تحديد غيره (قيد الفرادة في القاعدة)."""
    stmt = (
        update(EmployeeQualification)
        .where(
            EmployeeQualification.employee_id == employee_id,
            EmployeeQualification.is_hiring_qualification.is_(True),
        )
        .values(is_hiring_qualification=False)
    )
    if keep_id is not None:
        stmt = stmt.where(EmployeeQualification.id != keep_id)
    await db.execute(stmt)


async def add_qualification(
    db: AsyncSession, actor: User, employee_id: int, data: QualificationIn
) -> EmployeeQualification:
    emp = await locked_employee(db, actor, employee_id)
    if data.is_hiring_qualification:
        await _clear_hiring(db, emp.id, None)
    q = EmployeeQualification(
        employee_id=emp.id, created_by_user_id=actor.id, **data.model_dump()
    )
    db.add(q)
    await db.flush()
    add_log(db, emp.id, actor.id, "qualification", None, _q_summary(q))
    await db.commit()
    return q


async def _get_qualification(db, emp_id: int, qid: int) -> EmployeeQualification:
    q = await db.scalar(
        select(EmployeeQualification)
        .where(EmployeeQualification.id == qid, EmployeeQualification.employee_id == emp_id)
        .with_for_update()
    )
    if q is None:
        raise _bad(404, "المؤهل غير موجود")
    return q


async def patch_qualification(
    db: AsyncSession, actor: User, employee_id: int, qid: int, patch: QualificationPatch
) -> EmployeeQualification:
    emp = await locked_employee(db, actor, employee_id)
    q = await _get_qualification(db, emp.id, qid)
    fields = set(patch.model_fields_set)
    if not fields:
        raise _bad(422, "لم تُرسل أي حقول للتعديل")
    if "qualification_level" in fields and patch.qualification_level is None:
        raise _bad(422, "لا يمكن إفراغ المؤهل العلمي")
    if "is_hiring_qualification" in fields and patch.is_hiring_qualification is None:
        raise _bad(422, "قيمة مؤهل التعيين يجب أن تكون true أو false")

    old = _q_summary(q)
    if patch.is_hiring_qualification is True:
        await _clear_hiring(db, emp.id, q.id)
    for f in fields:
        setattr(q, f, getattr(patch, f))
    await db.flush()
    add_log(db, emp.id, actor.id, "qualification", old, _q_summary(q))
    await db.commit()
    return q


async def delete_qualification(
    db: AsyncSession, actor: User, employee_id: int, qid: int
) -> None:
    emp = await locked_employee(db, actor, employee_id)
    q = await _get_qualification(db, emp.id, qid)
    add_log(db, emp.id, actor.id, "qualification", _q_summary(q), None)
    await db.delete(q)
    await db.commit()


# ------------------------------------------------------------------ الدورات
async def list_trainings(db: AsyncSession, actor: User, employee_id: int):
    await visible_employee(db, actor, employee_id)
    rows = await db.scalars(
        select(EmployeeTraining)
        .where(EmployeeTraining.employee_id == employee_id)
        .order_by(EmployeeTraining.id)
    )
    return list(rows.all())


async def add_training(
    db: AsyncSession, actor: User, employee_id: int, data: TrainingIn
) -> EmployeeTraining:
    emp = await locked_employee(db, actor, employee_id)
    t = EmployeeTraining(
        employee_id=emp.id, created_by_user_id=actor.id, **data.model_dump()
    )
    db.add(t)
    await db.flush()
    add_log(db, emp.id, actor.id, "training", None, _t_summary(t))
    await db.commit()
    return t


async def _get_training(db, emp_id: int, tid: int) -> EmployeeTraining:
    t = await db.scalar(
        select(EmployeeTraining)
        .where(EmployeeTraining.id == tid, EmployeeTraining.employee_id == emp_id)
        .with_for_update()
    )
    if t is None:
        raise _bad(404, "الدورة غير موجودة")
    return t


async def patch_training(
    db: AsyncSession, actor: User, employee_id: int, tid: int, patch: TrainingPatch
) -> EmployeeTraining:
    emp = await locked_employee(db, actor, employee_id)
    t = await _get_training(db, emp.id, tid)
    fields = set(patch.model_fields_set)
    if not fields:
        raise _bad(422, "لم تُرسل أي حقول للتعديل")
    if "course_name" in fields and patch.course_name is None:
        raise _bad(422, "لا يمكن إفراغ اسم الدورة")
    old = _t_summary(t)
    for f in fields:
        setattr(t, f, getattr(patch, f))
    await db.flush()
    add_log(db, emp.id, actor.id, "training", old, _t_summary(t))
    await db.commit()
    return t


async def delete_training(db: AsyncSession, actor: User, employee_id: int, tid: int) -> None:
    emp = await locked_employee(db, actor, employee_id)
    t = await _get_training(db, emp.id, tid)
    add_log(db, emp.id, actor.id, "training", _t_summary(t), None)
    await db.delete(t)
    await db.commit()