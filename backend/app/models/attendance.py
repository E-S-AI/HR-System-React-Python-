from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

_SOURCE_TYPES = "('EXCEL_IMPORT', 'PLATFORM_SYNC', 'MANUAL')"
_SYNC_SOURCES = "('EXCEL_IMPORT', 'PLATFORM_API')"


class BiometricDevice(Base):
    __tablename__ = "biometric_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_name: Mapped[str] = mapped_column(String(200))
    platform_url: Mapped[str | None] = mapped_column(String(500))
    org_unit_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("org_units.id"), index=True
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AttendanceSyncLog(Base):
    __tablename__ = "attendance_sync_logs"
    __table_args__ = (
        CheckConstraint(
            f"sync_source IN {_SYNC_SOURCES}",
            name="ck_sync_logs_source",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("biometric_devices.id"), index=True
    )
    sync_source: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_fetched: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    records_inserted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    records_duplicated: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    unmapped_users_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error_details: Mapped[str | None] = mapped_column(Text)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("biometric_user_id", "attendance_date", name="uq_att_user_date"),
        Index("ix_att_employee_date", "employee_id", "attendance_date"),
        Index("ix_att_date", "attendance_date"),
        CheckConstraint(
            f"source_type IN {_SOURCE_TYPES}",
            name="ck_att_source_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # 7 platform columns
    biometric_user_id: Mapped[str] = mapped_column(String(100))
    biometric_employee_name: Mapped[str | None] = mapped_column(String(300))
    attendance_date: Mapped[date] = mapped_column(Date)
    first_in: Mapped[time | None] = mapped_column(Time)
    last_out: Mapped[time | None] = mapped_column(Time)
    platform_status: Mapped[str | None] = mapped_column(String(100))
    platform_directorate: Mapped[str | None] = mapped_column(String(300))

    # resolved fields
    work_schedule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("work_schedules.id")
    )
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), index=True
    )
    linked_leave_request_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("leave_requests.id")
    )

    # computed deduction fields
    late_minutes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    early_leave_minutes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_late_beyond_cutoff: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    is_early_leave_beyond_cutoff: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    counted_as_hourly_leave: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    hourly_leave_minutes_charged: Mapped[int] = mapped_column(
        Integer, server_default=text("0")
    )
    final_system_status: Mapped[str | None] = mapped_column(String(50))

    # source / audit
    source_type: Mapped[str] = mapped_column(String(30), server_default=text("'EXCEL_IMPORT'"))
    import_job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("import_jobs.id")
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
