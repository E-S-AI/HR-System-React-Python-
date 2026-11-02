from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_enrolling_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    TokenResponse,
    TwoFAConfirm,
    TwoFASetupResponse,
)
from app.services import twofa
from app.services.auth import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user, scope = await authenticate(
        db, data.phone_number.strip(), data.password, data.pin, data.otp
    )
    return TokenResponse(
        access_token=create_access_token(user.id, scope),
        requires_2fa_enrollment=(scope == "enroll"),
    )


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    return MeResponse(
        id=user.id,
        phone_number=user.phone_number,
        employee_id=user.employee_id,
        is_super_admin=user.is_super_admin,
        roles=[r.code for r in user.roles],
    )


@router.post("/2fa/setup", response_model=TwoFASetupResponse)
async def setup_2fa(user: User = Depends(get_enrolling_user)):
    return twofa.begin_setup(user)


@router.post("/2fa/confirm", response_model=TokenResponse)
async def confirm_2fa(
    data: TwoFAConfirm,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_enrolling_user),
):
    await twofa.confirm_setup(db, user, data.setup_token, data.code)
    return TokenResponse(access_token=create_access_token(user.id, "full"))