from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    module_name: Mapped[str] = mapped_column(String(40))
    original_file_name: Mapped[str] = mapped_column(String(255))
    sheet_name: Mapped[str | None] = mapped_column(String(100))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    import_mode: Mapped[str] = mapped_column(String(30))
    total_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    valid_new_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    valid_update_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    duplicate_rows: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(30))
    column_mapping: Mapped[dict | None] = mapped_column(JSONB)
    created_by_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportJobError(Base):
    __tablename__ = "import_job_errors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    import_job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_jobs.id"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    column_name: Mapped[str | None] = mapped_column(String(100))
    raw_value: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str] = mapped_column(String(50))
    error_message_ar: Mapped[str] = mapped_column(Text)