from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

STATUSES = (
    "AWAITING_PAPER",
    "PENDING_HR_APPROVAL",
    "APPROVED",
    "REJECTED_BY_HR",
    "REJECTED_PAST_72H_DATE",
    "AUTO_REJECTED_72H_NO_PAPER",
    "CANCELLED_BY_EMPLOYEE",
)
_STATUS_SQL = ", ".join(f"'{s}'" for s in STATUSES)


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_leave_requests_dates"),
        CheckConstraint("duration_minutes >= 0", name="ck_leave_requests_duration"),
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="ck_leave_requests_status"),
        CheckConstraint(
            "entry_source IN ('EMPLOYEE_PORTAL', 'HR_DIRECT_DECISION')",
            name="ck_leave_requests_source",
        ),
        Index("ix_leave_requests_status_deadline", "status", "attachment_deadline_at"),
        Index("ix_leave_requests_emp_start", "employee_id", "start_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"))
    leave_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("leave_types.id"))
    entry_source: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    duration_days: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default=text("0"))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)

    generated_printable_pdf_path: Mapped[str | None] = mapped_column(String(500))
    paper_attachment_path: Mapped[str | None] = mapped_column(String(500))
    attachment_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attachment_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hr_decision_number: Mapped[str | None] = mapped_column(String(100))

    status: Mapped[str] = mapped_column(String(40))
    hr_reviewer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    hr_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hr_notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LeaveApprovalLog(Base):
    __tablename__ = "leave_approval_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    leave_request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("leave_requests.id"), index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40))
    action_type: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )