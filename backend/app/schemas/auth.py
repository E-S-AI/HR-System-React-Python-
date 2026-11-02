from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    phone_number: str
    password: str
    pin: str | None = Field(default=None, pattern=r"^\d{6}$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    phone_number: str
    employee_id: int | None
    is_super_admin: bool
    roles: list[str]