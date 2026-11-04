from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExportLog(Base):
    __tablename__ = "export_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exported_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True
    )
    module_name: Mapped[str] = mapped_column(String(50))
    applied_filters: Mapped[dict | None] = mapped_column(JSONB)
    selected_columns: Mapped[list | None] = mapped_column(JSONB)
    exported_rows_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    exported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )