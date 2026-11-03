from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Governorate, OrgUnit, User, UserScope
from app.schemas.org import OrgUnitCreate, OrgUnitUpdate, ScopeCreate

MAX_LEVEL = 5


async def _check_governorate(db: AsyncSession, code: str | None) -> None:
    if code and not await db.scalar(
        select(Governorate.id).where(Governorate.governorate_code == code)
    ):
        raise HTTPException(status_code=422, detail="رمز المحافظة غير موجود")


async def create_org_unit(db: AsyncSession, data: OrgUnitCreate) -> OrgUnit:
    level = 1
    governorate = data.governorate_code
    if data.parent_id is not None:
        parent = await db.get(OrgUnit, data.parent_id)
        if parent is None:
            raise HTTPException(status_code=422, detail="الوحدة الأب غير موجودة")
        level = parent.level_number + 1
        if level > MAX_LEVEL:
            raise HTTPException(
                status_code=422, detail="الحد الأقصى للمستويات التنظيمية 5"
            )
        governorate = governorate or parent.governorate_code
    await _check_governorate(db, governorate)

    unit = OrgUnit(
        code=data.code.strip(),
        name_ar=data.name_ar.strip(),
        level_number=level,
        governorate_code=governorate,
        parent_id=data.parent_id,
    )
    db.add(unit)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="كود الوحدة مستخدم مسبقاً")
    await db.refresh(unit)
    return unit


async def update_org_unit(
    db: AsyncSession, unit_id: int, data: OrgUnitUpdate
) -> OrgUnit:
    unit = await db.get(OrgUnit, unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="الوحدة غير موجودة")
    if data.name_ar is not None:
        unit.name_ar = data.name_ar.strip()
    if data.is_active is not None:
        unit.is_active = data.is_active
    await db.commit()
    await db.refresh(unit)
    return unit


async def list_scopes(db: AsyncSession, user_id: int) -> list[UserScope]:
    rows = await db.scalars(
        select(UserScope).where(UserScope.user_id == user_id).order_by(UserScope.id)
    )
    return list(rows.all())


async def add_scope(db: AsyncSession, user_id: int, data: ScopeCreate) -> UserScope:
    if await db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="الحساب غير موجود")
    if data.org_unit_id is not None and await db.get(OrgUnit, data.org_unit_id) is None:
        raise HTTPException(status_code=422, detail="الوحدة التنظيمية غير موجودة")
    await _check_governorate(db, data.governorate_code)

    duplicate = await db.scalar(
        select(UserScope.id).where(
            UserScope.user_id == user_id,
            UserScope.org_unit_id == data.org_unit_id,
            UserScope.governorate_code == data.governorate_code,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="هذا النطاق مضاف مسبقاً")

    scope = UserScope(
        user_id=user_id,
        org_unit_id=data.org_unit_id,
        governorate_code=data.governorate_code,
        include_sub_units=data.include_sub_units,
    )
    db.add(scope)
    await db.commit()
    await db.refresh(scope)
    return scope


async def delete_scope(db: AsyncSession, user_id: int, scope_id: int) -> None:
    scope = await db.scalar(
        select(UserScope).where(UserScope.id == scope_id, UserScope.user_id == user_id)
    )
    if scope is None:
        raise HTTPException(status_code=404, detail="النطاق غير موجود")
    await db.delete(scope)
    await db.commit()