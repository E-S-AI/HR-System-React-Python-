from datetime import date, datetime

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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmployeeAssignment(Base):
    __tablename__ = "employee_assignments"
    __table_args__ = (
        Index("uq_assignment_emp_seq", "employee_id", "sequence_number", unique=True),
        Index(
            "uq_assignment_current",
            "employee_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        CheckConstraint(
            "action_type IN ('INITIAL_ASSIGNMENT', 'RENEWAL', 'ENDED')",
            name="ck_assignment_action",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_assignment_dates"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"))
    sequence_number: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    action_type: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    duration_text: Mapped[str | None] = mapped_column(String(100))
    assigned_position_or_unit: Mapped[str | None] = mapped_column(String(200))
    decision_number: Mapped[str | None] = mapped_column(String(100))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_hr_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )