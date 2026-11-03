from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import OrgUnit, User
from app.schemas.org import (
    OrgUnitCreate,
    OrgUnitRead,
    OrgUnitUpdate,
    ScopeCreate,
    ScopeRead,
)
from app.services import org as svc

router = APIRouter(tags=["org"])

admin_only = require_roles("CENTRAL_ADMIN")
hr_or_admin = require_roles("CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR")


@router.post("/org-units", response_model=OrgUnitRead, status_code=201)
async def create_unit(
    data: OrgUnitCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_only),
):
    return await svc.create_org_unit(db, data)


@router.get("/org-units", response_model=list[OrgUnitRead])
async def list_units(
    db: AsyncSession = Depends(get_db), _: User = Depends(hr_or_admin)
):
    rows = await db.scalars(select(OrgUnit).order_by(OrgUnit.level_number, OrgUnit.id))
    return rows.all()


@router.patch("/org-units/{unit_id}", response_model=OrgUnitRead)
async def update_unit(
    unit_id: int,
    data: OrgUnitUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_only),
):
    return await svc.update_org_unit(db, unit_id, data)


@router.get("/users/{user_id}/scopes", response_model=list[ScopeRead])
async def get_scopes(
    user_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(admin_only)
):
    return await svc.list_scopes(db, user_id)


@router.post("/users/{user_id}/scopes", response_model=ScopeRead, status_code=201)
async def add_scope(
    user_id: int,
    data: ScopeCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_only),
):
    return await svc.add_scope(db, user_id, data)


@router.delete("/users/{user_id}/scopes/{scope_id}", status_code=204)
async def remove_scope(
    user_id: int,
    scope_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_only),
):
    await svc.delete_scope(db, user_id, scope_id)