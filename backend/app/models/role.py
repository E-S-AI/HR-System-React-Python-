from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name_ar: Mapped[str] = mapped_column(String(100))


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", BigInteger, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)