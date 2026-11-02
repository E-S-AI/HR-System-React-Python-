from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status_code=401, detail="يجب تسجيل الدخول")
    if creds is None:
        raise unauthorized
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise unauthorized
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_roles(*codes: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.is_super_admin or {r.code for r in user.roles} & set(codes):
            return user
        raise HTTPException(status_code=403, detail="لا تملك صلاحية لهذه العملية")

    return checker