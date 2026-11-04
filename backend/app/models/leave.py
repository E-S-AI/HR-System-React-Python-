from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LeaveType(Base):
    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name_ar: Mapped[str] = mapped_column(String(100))
    allow_employee_request: Mapped[bool] = mapped_column(Boolean)
    workflow_path: Mapped[str] = mapped_column(String(30))
    deducts_balance: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    deducts_from_type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("leave_types.id")
    )
    min_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    max_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    enforce_72h_rule: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    max_past_entry_hours: Mapped[int | None] = mapped_column(
        Integer, server_default=text("72")
    )
    paper_upload_grace_hours: Mapped[int | None] = mapped_column(
        Integer, server_default=text("72")
    )
    printable_pdf_template_path: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class ServiceLeaveTier(Base):
    __tablename__ = "service_leave_tiers"
    __table_args__ = (
        Index("uq_tier_type_min", "leave_type_id", "min_service_years", unique=True),
        CheckConstraint(
            "max_service_years IS NULL OR max_service_years > min_service_years",
            name="ck_tier_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    leave_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("leave_types.id"))
    min_service_years: Mapped[int] = mapped_column(Integer)
    max_service_years: Mapped[int | None] = mapped_column(Integer)
    entitled_days: Mapped[int] = mapped_column(Integer)


class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    __table_args__ = (
        Index("uq_balance_emp_type_year", "employee_id", "leave_type_id", "year", unique=True),
        CheckConstraint(
            "entitled_minutes >= 0 AND used_minutes >= 0 AND reserved_minutes >= 0",
            name="ck_balance_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id"))
    leave_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("leave_types.id"))
    year: Mapped[int] = mapped_column(Integer)
    service_years_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(4, 1), server_default=text("0")
    )
    minutes_per_day: Mapped[int] = mapped_column(Integer, server_default=text("420"))
    entitled_minutes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    used_minutes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    reserved_minutes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LeaveTransaction(Base):
    __tablename__ = "leave_transactions"
    __table_args__ = (
        Index("uq_tx_request_type", "leave_request_id", "transaction_type", unique=True),
        Index("ix_tx_balance_created", "balance_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    balance_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("leave_balances.id"))
    # المفتاحان الأجنبيان يُضافان عند إنشاء جدولي leave_requests و attendance_records
    leave_request_id: Mapped[int | None] = mapped_column(BigInteger)
    attendance_record_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    transaction_type: Mapped[str] = mapped_column(String(40))
    delta_minutes: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(255))
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )