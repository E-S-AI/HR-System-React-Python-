from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import LoginRequest, MeResponse, TokenResponse
from app.services.auth import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate(db, data.phone_number.strip(), data.password, data.pin)
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    return MeResponse(
        id=user.id,
        phone_number=user.phone_number,
        employee_id=user.employee_id,
        is_super_admin=user.is_super_admin,
        roles=[r.code for r in user.roles],
    )