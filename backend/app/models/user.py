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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.role import Role


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(require_google_auth = false AND static_login_pin_hash IS NOT NULL) "
            "OR (require_google_auth = true AND google_auth_secret_encrypted IS NOT NULL)",
            name="ck_users_auth_method",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(30), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    static_login_pin_hash: Mapped[str | None] = mapped_column(String(255))
    pin_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pin_reset_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    require_google_auth: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    google_auth_secret_encrypted: Mapped[str | None] = mapped_column(String(255))
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id"), unique=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    password_reset_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    password_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_super_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", lazy="selectin")