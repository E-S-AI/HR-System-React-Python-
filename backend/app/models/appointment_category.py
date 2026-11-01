from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppointmentCategory(Base):
    __tablename__ = "appointment_categories_matrix"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_code: Mapped[str] = mapped_column(String(10), unique=True)
    category_label_ar: Mapped[str] = mapped_column(String(150), unique=True)
    employment_type: Mapped[str] = mapped_column(String(50))