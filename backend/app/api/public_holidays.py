from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.database import get_db
from app.models import User
from app.schemas.holiday import HolidayCreate, HolidayCreateResult, HolidayRead
from app.services import holidays as svc

router = APIRouter(prefix="/public-holidays", tags=["public-holidays"])

manage = require_roles("CENTRAL_ADMIN", "CENTRAL_HR")


@router.get("", response_model=list[HolidayRead])
async def list_holidays(
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await svc.list_holidays(db, year or date.today().year)


@router.post("", response_model=HolidayCreateResult, status_code=201)
async def add_holidays(
    data: HolidayCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(manage),
):
    created, skipped, affected = await svc.create_holidays(db, actor, data)
    return HolidayCreateResult(
        created=[HolidayRead.model_validate(h) for h in created],
        skipped_existing=skipped,
        affected_requests=affected,
    )


@router.delete("/{holiday_id}", status_code=204)
async def remove_holiday(
    holiday_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(manage),
):
    await svc.delete_holiday(db, holiday_id)