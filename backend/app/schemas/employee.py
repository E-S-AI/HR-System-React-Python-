from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class EmployeeCreate(BaseModel):
    governorate_code: str
    org_unit_id: int | None = None
    appointment_category_code: str | None = None
    biometric_code: str | None = None

    first_name: str
    father_name: str | None = None
    last_name: str
    mother_full_name: str | None = None
    national_id: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    birth_place: str | None = None
    marital_status: str | None = None
    phone_number: str

    job_title_name: str | None = None
    permanent_or_contract: str | None = None
    employment_status: str | None = None

    state_start_date: date
    hire_date: date | None = None
    work_start_date: date | None = None

    @field_validator("*", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                return None
        return v


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    global_serial_number: int
    formatted_serial: str
    employee_code: str | None
    governorate_code: str
    org_unit_id: int | None
    appointment_category_code: str | None
    biometric_code: str | None
    first_name: str
    father_name: str | None
    last_name: str
    full_name_spaced: str
    national_id: str | None
    phone_number: str
    permanent_or_contract: str
    state_start_date: date
    created_at: datetime


class CategoryAssign(BaseModel):
    category_code: str