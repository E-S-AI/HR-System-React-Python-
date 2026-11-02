from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User
from app.services.users import is_privileged

bearer = HTTPBearer(auto_error=False)


async def _load(creds: HTTPAuthorizationCredentials | None, db: AsyncSession):
    unauthorized = HTTPException(status_code=401, detail="يجب تسجيل الدخول")
    if creds is None:
        raise unauthorized
    decoded = decode_access_token(creds.credentials)
    if decoded is None:
        raise unauthorized
    user_id, scope = decoded
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user, scope


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    user, scope = await _load(creds, db)
    # نفحص حالة الحساب من القاعدة لا من التوكن فقط (يغطي إعادة تعيين المصادقة)
    if scope != "full" or (is_privileged(user) and not user.require_google_auth):
        raise HTTPException(
            status_code=403,
            detail="يجب تفعيل Google Authenticator أولاً قبل متابعة العمل",
        )
    return user


async def get_enrolling_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    user, _ = await _load(creds, db)
    return user


def require_roles(*codes: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.is_super_admin or {r.code for r in user.roles} & set(codes):
            return user
        raise HTTPException(status_code=403, detail="لا تملك صلاحية لهذه العملية")

    return checker