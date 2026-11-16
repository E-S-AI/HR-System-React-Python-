from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import User
from app.schemas.audit_log import AuditLogRead
from app.services.audit import list_audit_logs

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])
admin_only = require_roles("CENTRAL_ADMIN")


@router.get("", response_model=list[AuditLogRead])
async def get_audit_logs(
    user_id: int | None = None,
    action_type: str | None = None,
    target_table: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_only),
):
    """عرض سجل التدقيق الأمني الشامل (لمسؤول الإدارة المركزية حصراً)."""
    return await list_audit_logs(
        db,
        user_id=user_id,
        action_type=action_type,
        target_table=target_table,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )