from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmployeeQualification(Base):
    __tablename__ = "employee_qualifications"
    __table_args__ = (
        Index(
            "uq_employee_hiring_qualification",
            "employee_id",
            unique=True,
            postgresql_where=text("is_hiring_qualification"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id"), index=True
    )
    qualification_level: Mapped[str] = mapped_column(String(100))
    specialization: Mapped[str | None] = mapped_column(String(150))
    issuing_institution: Mapped[str | None] = mapped_column(String(150))
    graduation_year: Mapped[str | None] = mapped_column(String(20))
    is_hiring_qualification: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EmployeeTraining(Base):
    __tablename__ = "employee_trainings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id"), index=True
    )
    course_name: Mapped[str] = mapped_column(String(200))
    training_provider: Mapped[str | None] = mapped_column(String(150))
    course_date: Mapped[str | None] = mapped_column(String(50))
    duration_text: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )