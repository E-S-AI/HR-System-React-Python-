from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BalanceRead(BaseModel):
    id: int
    employee_id: int
    leave_type_code: str
    leave_type_name_ar: str
    year: int
    service_years_snapshot: float
    minutes_per_day: int
    entitled_minutes: int
    used_minutes: int
    reserved_minutes: int
    remaining_minutes: int
    remaining_days: float


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_type: str
    delta_minutes: int
    notes: str | None
    created_by_user_id: int | None
    created_at: datetime


class GrantRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    employee_id: int | None = None


class GrantResult(BaseModel):
    year: int
    created: int
    minutes_per_day: int


class RecalcRequest(BaseModel):
    employee_id: int
    year: int = Field(ge=2000, le=2100)


class AdjustRequest(BaseModel):
    employee_id: int
    year: int = Field(ge=2000, le=2100)
    delta_minutes: int = Field(ge=-200000, le=200000)
    notes: str = Field(min_length=5, max_length=255)