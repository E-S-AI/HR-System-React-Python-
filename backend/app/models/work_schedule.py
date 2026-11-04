from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkSchedule(Base):
    __tablename__ = "work_schedules"
    __table_args__ = (
        CheckConstraint(
            "official_end_time > official_start_time", name="ck_work_schedules_times"
        ),
        CheckConstraint(
            "effective_to_date IS NULL OR effective_to_date >= effective_from_date",
            name="ck_work_schedules_dates",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_name_ar: Mapped[str] = mapped_column(String(150))
    official_start_time: Mapped[time] = mapped_column(
        Time, server_default=text("'08:00:00'")
    )
    official_end_time: Mapped[time] = mapped_column(
        Time, server_default=text("'15:00:00'")
    )
    late_grace_minutes: Mapped[int] = mapped_column(Integer, server_default=text("20"))
    early_leave_grace_minutes: Mapped[int] = mapped_column(
        Integer, server_default=text("20")
    )
    late_cutoff_time: Mapped[time] = mapped_column(
        Time, server_default=text("'08:20:00'")
    )
    early_leave_cutoff_time: Mapped[time] = mapped_column(
        Time, server_default=text("'14:40:00'")
    )
    workday_minutes: Mapped[int] = mapped_column(Integer, server_default=text("420"))
    effective_from_date: Mapped[date] = mapped_column(Date)
    effective_to_date: Mapped[date | None] = mapped_column(Date)
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )