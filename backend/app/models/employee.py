from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # --- الكود والرقم التسلسلي ---
    global_serial_number: Mapped[int] = mapped_column(
        BigInteger, unique=True, server_default=text("nextval('employee_global_serial_seq')")
    )
    formatted_serial: Mapped[str] = mapped_column(String(12))
    governorate_code: Mapped[str] = mapped_column(
        String(10), ForeignKey("governorates_matrix.governorate_code"), index=True
    )
    appointment_category_code: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("appointment_categories_matrix.category_code")
    )
    employee_code: Mapped[str | None] = mapped_column(String(50), unique=True)
    self_registry_number: Mapped[int | None] = mapped_column(BigInteger)
    biometric_code: Mapped[str | None] = mapped_column(String(50), unique=True)

    # --- الأسماء والبيانات الشخصية ---
    first_name: Mapped[str] = mapped_column(String(100))
    father_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    full_name_spaced: Mapped[str] = mapped_column(String(300))
    mother_full_name: Mapped[str | None] = mapped_column(String(200))
    national_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    gender: Mapped[str | None] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(Date)
    birth_place: Mapped[str | None] = mapped_column(String(150))

    # --- القيود المدنية والسكن ---
    country: Mapped[str | None] = mapped_column(String(100))
    civil_reg_governorate: Mapped[str | None] = mapped_column(String(100))
    civil_reg_secretariat: Mapped[str | None] = mapped_column(String(150))
    civil_reg_place: Mapped[str | None] = mapped_column(String(150))
    civil_reg_number: Mapped[str | None] = mapped_column(String(50))
    marital_status: Mapped[str | None] = mapped_column(String(50))
    wives_count: Mapped[int | None] = mapped_column(Integer, server_default=text("0"))
    children_count: Mapped[int | None] = mapped_column(Integer, server_default=text("0"))
    children_details: Mapped[str | None] = mapped_column(Text)
    residence_governorate: Mapped[str | None] = mapped_column(String(100))
    residence_city_region: Mapped[str | None] = mapped_column(String(150))
    residence_address_detail: Mapped[str | None] = mapped_column(Text)

    # --- الهيكل التنظيمي (FK يُضاف لاحقاً) ---
    org_unit_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("org_units.id"), index=True
    )
    org_levels_import_raw: Mapped[dict | None] = mapped_column(JSONB)

    # --- البيانات الوظيفية ---
    job_title_name: Mapped[str | None] = mapped_column(String(200))
    job_classification: Mapped[str | None] = mapped_column(String(150))
    current_job_category: Mapped[str | None] = mapped_column(String(50))
    job_rank: Mapped[str | None] = mapped_column(String(50))
    job_grade: Mapped[str | None] = mapped_column(String(50))
    permanent_or_contract: Mapped[str] = mapped_column(String(50))
    employment_pattern: Mapped[str | None] = mapped_column(String(150))
    employment_status: Mapped[str | None] = mapped_column(String(100))
    status_details: Mapped[str | None] = mapped_column(Text)
    merger_details: Mapped[str | None] = mapped_column(Text)
    qualifications_excel_raw: Mapped[str | None] = mapped_column(Text)

    # --- التواريخ والتكليف ---
    state_start_date: Mapped[date] = mapped_column(Date)
    hire_date: Mapped[date | None] = mapped_column(Date)
    work_start_date: Mapped[date | None] = mapped_column(Date)
    ministry_start_date: Mapped[date | None] = mapped_column(Date)
    termination_date: Mapped[date | None] = mapped_column(Date)
    assignment_start_date: Mapped[date | None] = mapped_column(Date)
    assignment_end_date: Mapped[date | None] = mapped_column(Date)
    assignment_duration: Mapped[str | None] = mapped_column(String(100))
    assignment_renewal_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    # --- التواصل ---
    phone_number: Mapped[str] = mapped_column(String(30))
    electronic_account: Mapped[str | None] = mapped_column(String(150))
    sham_cash_account: Mapped[str | None] = mapped_column(String(100))
    addition_request_info: Mapped[str | None] = mapped_column(Text)
    central_notes: Mapped[str | None] = mapped_column(Text)

    updated_by_hr_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )