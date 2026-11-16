from datetime import date, datetime, time, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


def log_audit(
    db: AsyncSession,
    *,
    user_id: int | None,
    action_type: str,
    target_table: str,
    target_record_id: str | int | None = None,
    org_unit_id: int | None = None,
    old_data: dict | None = None,
    new_data: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    row = AuditLog(
        user_id=user_id,
        org_unit_id=org_unit_id,
        action_type=action_type,
        target_table=target_table,
        target_record_id=str(target_record_id) if target_record_id is not None else None,
        old_data=old_data,
        new_data=new_data,
        ip_address=ip_address,
    )
    db.add(row)
    return row


async def list_audit_logs(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    action_type: str | None = None,
    target_table: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[AuditLog]:
    stmt = select(AuditLog)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action_type:
        stmt = stmt.where(AuditLog.action_type == action_type)
    if target_table:
        stmt = stmt.where(AuditLog.target_table == target_table)
    if date_from:
        start_dt = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        stmt = stmt.where(AuditLog.created_at >= start_dt)
    if date_to:
        end_dt = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        stmt = stmt.where(AuditLog.created_at <= end_dt)

    rows = await db.scalars(
        stmt.order_by(AuditLog.id.desc()).offset(skip).limit(limit)
    )
    return list(rows.all())