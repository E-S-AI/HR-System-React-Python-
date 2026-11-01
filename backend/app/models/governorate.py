from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Governorate(Base):
    __tablename__ = "governorates_matrix"

    id: Mapped[int] = mapped_column(primary_key=True)
    governorate_name_ar: Mapped[str] = mapped_column(String(100), unique=True)
    governorate_name_en: Mapped[str] = mapped_column(String(100), unique=True)
    governorate_code: Mapped[str] = mapped_column(String(10), unique=True)