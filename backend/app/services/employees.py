from datetime import date

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AppointmentCategory,
    Employee,
    EmployeeChangeLog,
    EmployeeQualification,
    EmployeeTraining,
    Governorate,
    OrgUnit,
    User,
    EmployeeAssignment,
)
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeDetail,
    EmployeePatch,
    QualificationRead,
    TrainingRead,
)
from app.schemas.exports import EmployeeExportFilters
from app.schemas.user import UserCreate
from app.services.employee_export import build_conditions
from app.services.leave_balances import grant_year, recalc_balances_from_year, visible_employee
from app.services.scope import get_scope
from app.services.users import create_employee_account

UNIQUE_MESSAGES = {
    "national_id": "الرقم الوطني مسجل مسبقاً لموظف آخر",
    "biometric_code": "رقم البصمة مسجل مسبقاً لموظف آخر",
    "employee_code": "كود الموظف مكرر",
}

NOT_NULL = {
    "governorate_code", "first_name", "last_name", "phone_number",
    "state_start_date", "permanent_or_contract", "assignment_renewal_count",
}
SENSITIVE = {
    "state_start_date", "national_id", "phone_number", "permanent_or_contract",
    "termination_date", "governorate_code", "biometric_code",
}
NAME_FIELDS = {"first_name", "father_name", "last_name"}

ASSIGNMENT_FIELDS = {
    "assignment_start_date", "assignment_end_date",
    "assignment_duration", "assignment_renewal_count",
}


def _bad(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _s(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _unique_error(exc: IntegrityError) -> HTTPException:
    text_error = str(exc.orig)
    for field, message in UNIQUE_MESSAGES.items():
        if field in text_error:
            return _bad(409, message)
    return _bad(409, "بيانات مكررة أو غير صالحة")


# ------------------------------------------------------------------ القراءة
async def build_detail(db: AsyncSession, emp: Employee) -> EmployeeDetail:
    quals = (
        await db.scalars(
            select(EmployeeQualification)
            .where(EmployeeQualification.employee_id == emp.id)
            .order_by(EmployeeQualification.id)
        )
    ).all()
    trainings = (
        await db.scalars(
            select(EmployeeTraining)
            .where(EmployeeTraining.employee_id == emp.id)
            .order_by(EmployeeTraining.id)
        )
    ).all()
    user = await db.scalar(select(User).where(User.employee_id == emp.id))

    age = None
    if emp.birth_date:
        t = date.today()
        age = t.year - emp.birth_date.year - ((t.month, t.day) < (emp.birth_date.month, emp.birth_date.day))
    underscored = "_".join(emp.full_name_spaced.split()) if emp.full_name_spaced else None

    detail = EmployeeDetail.model_validate(emp)
    return detail.model_copy(
        update={
            "age": age,
            "full_name_underscored": underscored,
            "qualifications": [QualificationRead.model_validate(q) for q in quals],
            "trainings": [TrainingRead.model_validate(t) for t in trainings],
            "account_user_id": user.id if user else None,
            "account_active": user.is_active if user else None,
        }
    )


async def get_detail(db: AsyncSession, actor: User, employee_id: int) -> EmployeeDetail:
    emp = await visible_employee(db, actor, employee_id)
    return await build_detail(db, emp)


async def list_employees(
    db: AsyncSession, actor: User, filters: EmployeeExportFilters, skip: int, limit: int
) -> list[Employee]:
    conds = await build_conditions(db, actor, filters)
    rows = await db.scalars(
        select(Employee).where(*conds).order_by(Employee.id).offset(skip).limit(limit)
    )
    return list(rows.all())


async def list_changes(
    db: AsyncSession, actor: User, employee_id: int, skip: int, limit: int
) -> list[EmployeeChangeLog]:
    await visible_employee(db, actor, employee_id)
    rows = await db.scalars(
        select(EmployeeChangeLog)
        .where(EmployeeChangeLog.employee_id == employee_id)
        .order_by(EmployeeChangeLog.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(rows.all())


# ------------------------------------------------------------------ الإنشاء
async def create_employee(
    db: AsyncSession, data: EmployeeCreate, actor: User
) -> tuple[Employee, dict]:
    scope = await get_scope(db, actor)
    if scope is not None and not scope.allows(data.governorate_code, data.org_unit_id):
        raise _bad(403, "هذه المحافظة أو الوحدة خارج نطاق صلاحيتك")

    governorate = await db.scalar(
        select(Governorate).where(Governorate.governorate_code == data.governorate_code)
    )
    if governorate is None:
        raise _bad(422, "رمز المحافظة غير موجود")
    if data.org_unit_id is not None and await db.get(OrgUnit, data.org_unit_id) is None:
        raise _bad(422, "الوحدة التنظيمية غير موجودة")

    category = None
    if data.appointment_category_code:
        category = await db.scalar(
            select(AppointmentCategory).where(
                AppointmentCategory.category_code == data.appointment_category_code
            )
        )
        if category is None:
            raise _bad(422, "رمز فئة التعيين غير موجود")

    permanent_or_contract = data.permanent_or_contract or (
        category.employment_type if category else None
    )
    if permanent_or_contract is None:
        raise _bad(422, "حدد (مثبت أو متعاقد) أو اختر فئة تعيين")
    if category and category.employment_type != permanent_or_contract:
        raise _bad(
            422,
            f"الفئة {category.category_code} تخص ({category.employment_type}) وتتعارض مع ({permanent_or_contract})",
        )
    if data.create_account is not None and await db.scalar(
        select(User.id).where(User.phone_number == data.phone_number)
    ):
        raise _bad(409, "رقم الهاتف مستخدم لحساب دخول آخر، لا يمكن إنشاء الحساب بهذا الرقم")
    if (
        data.assignment_start_date is not None
        and data.assignment_end_date is not None
        and data.assignment_end_date < data.assignment_start_date
    ):
        raise _bad(422, "تاريخ انتهاء التكليف قبل تاريخ بدايته")
    
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
    values = data.model_dump(
        exclude_none=True,
        exclude={
            "permanent_or_contract", "qualifications", "trainings",
            "create_account", "grant_leave_balance",
        },
    )
    employee = Employee(
        **values,
        permanent_or_contract=permanent_or_contract,
        global_serial_number=serial,
        formatted_serial=formatted,
        employee_code=code,
        full_name_spaced=full_name,
        updated_by_hr_id=actor.id,
    )
    db.add(employee)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _unique_error(exc)

    for q in data.qualifications:
        db.add(EmployeeQualification(employee_id=employee.id, created_by_user_id=actor.id, **q.model_dump()))
    for t in data.trainings:
        db.add(EmployeeTraining(employee_id=employee.id, created_by_user_id=actor.id, **t.model_dump()))
    if data.assignment_start_date is not None:
        db.add(
            EmployeeAssignment(
                employee_id=employee.id,
                sequence_number=1,
                action_type="INITIAL_ASSIGNMENT",
                start_date=data.assignment_start_date,
                end_date=data.assignment_end_date,
                duration_text=data.assignment_duration,
                is_current=True,
                created_by_hr_id=actor.id,
            )
        )
    db.add(
        EmployeeChangeLog(
            employee_id=employee.id,
            changed_by_user_id=actor.id,
            field_name="__created__",
            new_value=code,
            change_reason="إنشاء يدوي",
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _unique_error(exc)
    await db.refresh(employee)

    extras: dict = {"account": None, "balance_granted": False, "warnings": []}
    if data.create_account is not None:
        try:
            user, pin = await create_employee_account(
                db, actor, UserCreate(employee_id=employee.id, password=data.create_account.password)
            )
            extras["account"] = {
                "user_id": user.id,
                "phone_number": user.phone_number,
                "static_pin": pin,
            }
        except HTTPException as exc:
            extras["warnings"].append(f"حُفظ الموظف لكن تعذّر إنشاء الحساب: {exc.detail}")
    if data.grant_leave_balance:
        try:
            created, _ = await grant_year(db, date.today().year, employee.id, actor.id)
            extras["balance_granted"] = created > 0
            if created == 0:
                extras["warnings"].append(
                    "لم يُمنح رصيد إجازات (تاريخ بدء العمل بعد نهاية السنة أو خدمته منتهية)"
                )
        except HTTPException as exc:
            extras["warnings"].append(f"حُفظ الموظف لكن تعذّر منح الرصيد: {exc.detail}")
    return employee, extras


# ------------------------------------------------------------------ التعديل
async def patch_employee(
    db: AsyncSession, actor: User, employee_id: int, patch: EmployeePatch
):
    emp = await db.scalar(
        select(Employee).where(Employee.id == employee_id).with_for_update()
    )
    scope = await get_scope(db, actor)
    if emp is None or (
        scope is not None and not scope.allows(emp.governorate_code, emp.org_unit_id)
    ):
        raise _bad(404, "الموظف غير موجود")

    fields = set(patch.model_fields_set) - {"change_reason"}
    if not fields:
        raise _bad(422, "لم تُرسل أي حقول للتعديل")
    if fields & ASSIGNMENT_FIELDS:
        raise _bad(
            422, "حقول التكليف تُدار من مسار التكليفات: /employees/{id}/assignments"
        )
    for f in fields & NOT_NULL:
        if getattr(patch, f) is None:
            raise _bad(422, f"لا يمكن إفراغ الحقل ({f})")

    changes: dict[str, tuple] = {
        f: (getattr(emp, f), getattr(patch, f))
        for f in fields
        if getattr(emp, f) != getattr(patch, f)
    }
    if not changes:
        await db.commit()  # لا تغيير: نحرر القفل فقط
        return emp, [], 0, False

    reason = (patch.change_reason or "").strip() or None
    sensitive = sorted(set(changes) & SENSITIVE)
    if sensitive and (reason is None or len(reason) < 3):
        raise _bad(422, f"سبب التعديل مطلوب (3 أحرف فأكثر) عند تعديل: {', '.join(sensitive)}")

    def new_val(field: str):
        return changes[field][1] if field in changes else getattr(emp, field)

    if "governorate_code" in changes and await db.scalar(
        select(Governorate.id).where(Governorate.governorate_code == new_val("governorate_code"))
    ) is None:
        raise _bad(422, "رمز المحافظة غير موجود")
    if (
        "org_unit_id" in changes
        and new_val("org_unit_id") is not None
        and await db.get(OrgUnit, new_val("org_unit_id")) is None
    ):
        raise _bad(422, "الوحدة التنظيمية غير موجودة")
    if scope is not None and not scope.allows(new_val("governorate_code"), new_val("org_unit_id")):
        raise _bad(403, "التعديل ينقل الموظف إلى خارج نطاق صلاحيتك")

    new_cat, new_type = new_val("appointment_category_code"), new_val("permanent_or_contract")
    if "appointment_category_code" in changes or "permanent_or_contract" in changes:
        if new_cat:
            category = await db.scalar(
                select(AppointmentCategory).where(AppointmentCategory.category_code == new_cat)
            )
            if category is None:
                raise _bad(422, "رمز فئة التعيين غير موجود")
            if category.employment_type != new_type:
                raise _bad(
                    422,
                    f"فئة التعيين {new_cat} تخص ({category.employment_type}) وتتعارض مع ({new_type})، غيّرهما معاً",
                )
        elif emp.employee_code:
            raise _bad(422, "لا يمكن إفراغ فئة التعيين بعد توليد كود الموظف")
    if new_cat and emp.employee_code is None:
        # أول تحديد للفئة يولّد الكود الثابت
        changes["employee_code"] = (None, f"{new_val('governorate_code')}-{new_cat}-{emp.formatted_serial}")

    for f, (_, new_v) in changes.items():
        setattr(emp, f, new_v)
    if NAME_FIELDS & set(changes):
        emp.full_name_spaced = " ".join(
            p for p in (emp.first_name, emp.father_name, emp.last_name) if p
        )
    emp.updated_by_hr_id = actor.id
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _unique_error(exc)

    logs = [
        EmployeeChangeLog(
            employee_id=emp.id,
            changed_by_user_id=actor.id,
            field_name=f,
            old_value=_s(old),
            new_value=_s(new_v),
            change_reason=reason,
        )
        for f, (old, new_v) in changes.items()
    ]
    recalculated = 0
    deactivated = False
    try:
        if "state_start_date" in changes:
            recalculated = await recalc_balances_from_year(
                db, emp, actor.id, date.today().year
            )
        if "termination_date" in changes and changes["termination_date"][1] is not None:
            user = await db.scalar(
                select(User).where(User.employee_id == emp.id).with_for_update()
            )
            if user is not None and user.is_active:
                user.is_active = False
                deactivated = True
                logs.append(
                    EmployeeChangeLog(
                        employee_id=emp.id,
                        changed_by_user_id=actor.id,
                        field_name="account_is_active",
                        old_value="true",
                        new_value="false",
                        change_reason="تعطيل الحساب بسبب تحديد تاريخ إنهاء الخدمة",
                    )
                )
        db.add_all(logs)
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    await db.refresh(emp)
    return emp, sorted(f for f in changes if f != "employee_code"), recalculated, deactivated


# ------------------------------------------------------------------ تحديد الفئة لأول مرة
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
        raise _bad(404, "الموظف غير موجود")
    if employee.employee_code or employee.appointment_category_code:
        raise _bad(409, "كود الموظف مولّد مسبقاً وهو ثابت لا يتغير")

    category = await db.scalar(
        select(AppointmentCategory).where(AppointmentCategory.category_code == category_code)
    )
    if category is None:
        raise _bad(422, "رمز فئة التعيين غير موجود")
    if category.employment_type != employee.permanent_or_contract:
        raise _bad(
            422,
            f"الفئة {category_code} ({category.employment_type}) لا تناسب موظفاً {employee.permanent_or_contract}",
        )

    employee.appointment_category_code = category.category_code
    employee.employee_code = (
        f"{employee.governorate_code}-{category.category_code}-{employee.formatted_serial}"
    )
    employee.updated_by_hr_id = actor.id
    await db.commit()
    await db.refresh(employee)
    return employee