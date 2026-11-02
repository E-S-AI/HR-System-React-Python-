from datetime import datetime

from pydantic import BaseModel, Field

from typing import Literal

class UserCreate(BaseModel):
    employee_id: int
    password: str = Field(min_length=8, max_length=128)
    phone_number: str | None = None  # الافتراضي: هاتف الموظف


class UserCreated(BaseModel):
    id: int
    phone_number: str
    employee_id: int | None
    static_pin: str  # يظهر مرة واحدة فقط


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class PinResetResponse(BaseModel):
    static_pin: str  # يظهر مرة واحدة فقط


class StatusUpdate(BaseModel):
    is_active: bool


class UserRead(BaseModel):
    id: int
    phone_number: str
    employee_id: int | None
    is_active: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    roles: list[str]


class StaffCreate(BaseModel):
    phone_number: str
    password: str = Field(min_length=8, max_length=128)
    role_code: Literal["CENTRAL_ADMIN", "CENTRAL_HR", "DIRECTORATE_HR"]
    employee_id: int | None = None