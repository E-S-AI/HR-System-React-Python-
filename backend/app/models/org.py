from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrgUnit(Base):
    __tablename__ = "org_units"
    __table_args__ = (
        CheckConstraint("level_number BETWEEN 1 AND 5", name="ck_org_units_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name_ar: Mapped[str] = mapped_column(String(200))
    level_number: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    governorate_code: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("governorates_matrix.governorate_code")
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("org_units.id"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserScope(Base):
    __tablename__ = "user_scopes"
    __table_args__ = (
        CheckConstraint(
            "org_unit_id IS NOT NULL OR governorate_code IS NOT NULL",
            name="ck_user_scopes_target",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True
    )
    org_unit_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("org_units.id")
    )
    governorate_code: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("governorates_matrix.governorate_code")
    )
    include_sub_units: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true")
    )