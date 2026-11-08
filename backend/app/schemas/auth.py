from pydantic import BaseModel, Field , field_validator


class LoginRequest(BaseModel):
    phone_number: str
    password: str
    pin: str | None = Field(default=None, pattern=r"^\d{6}$")
    otp: str | None = Field(default=None, pattern=r"^\d{6}$")

    @field_validator("pin", "otp", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    requires_2fa_enrollment: bool = False


class MeResponse(BaseModel):
    id: int
    phone_number: str
    employee_id: int | None
    is_super_admin: bool
    roles: list[str]


class TwoFASetupResponse(BaseModel):
    setup_token: str
    secret: str
    otpauth_uri: str
    qr_svg_data_uri: str


class TwoFAConfirm(BaseModel):
    setup_token: str
    code: str = Field(pattern=r"^\d{6}$")