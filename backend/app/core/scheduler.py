import asyncio
import contextlib
import logging

from app.core.database import SessionLocal
from app.services.audit import log_audit
from app.services.leave_requests import auto_reject_overdue

logger = logging.getLogger(__name__)
INTERVAL_SECONDS = 600  # كل 10 دقائق


async def run_maintenance_once() -> int:
    """ينفذ دورة صيانة واحدة: رفض الطلبات المتجاوزة لمهلة 72 ساعة دون رفع الورقة."""
    async with SessionLocal() as db:
        rejected = await auto_reject_overdue(db)
        if rejected > 0:
            log_audit(
                db,
                user_id=None,
                action_type="AUTO_REJECT_72H_RUN",
                target_table="leave_requests",
                new_data={"rejected_count": rejected},
            )
            await db.commit()
            logger.info("Auto-rejected %d overdue leave requests", rejected)
        return rejected


async def _scheduler_loop() -> None:
    while True:
        try:
            await run_maintenance_once()
        except Exception:
            logger.exception("Background maintenance cycle failed")
        await asyncio.sleep(INTERVAL_SECONDS)


@contextlib.asynccontextmanager
async def scheduler_lifespan(app):
    task = asyncio.create_task(_scheduler_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task