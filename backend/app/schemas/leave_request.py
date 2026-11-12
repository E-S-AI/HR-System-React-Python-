from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LeaveRequestCreate(BaseModel):
    leave_type_code: Literal["ADMIN", "HOURLY", "MISSION"]
    start_date: date
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def blank_reason(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("تاريخ النهاية قبل تاريخ البداية")
        return self


class LeaveRequestRead(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_code: str | None
    leave_type_code: str
    leave_type_name_ar: str
    entry_source: str
    start_date: date
    end_date: date
    start_time: time
    end_time: time
    duration_days: float
    duration_minutes: int
    reason: str | None
    status: str
    paper_uploaded: bool
    attachment_uploaded_at: datetime | None
    attachment_deadline_at: datetime | None
    hr_reviewer_id: int | None
    hr_action_at: datetime | None
    hr_notes: str | None
    hr_decision_number: str | None
    created_at: datetime


class ApproveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)
    decision_number: str | None = Field(default=None, max_length=100)


class RejectRequest(BaseModel):
    notes: str = Field(min_length=3, max_length=1000)


class ApprovalLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    from_status: str | None
    to_status: str
    action_type: str
    comment: str | None
    created_at: datetime


class ExpireResult(BaseModel):
    rejected: int

DECISION_LEAVE_TYPES = ("UNPAID", "SICK", "MARRIAGE", "DEATH", "HAJJ")


class HRDirectDecisionCreate(BaseModel):
    """إجازة بقرار تُسجَّل مباشرة من الموارد البشرية (معتمدة، دون خصم من الرصيد)."""

    employee_id: int = Field(gt=0)
    leave_type_code: Literal["UNPAID", "SICK", "MARRIAGE", "DEATH", "HAJJ"]
    start_date: date
    end_date: date
    hr_decision_number: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("hr_decision_number", "reason", "notes", mode="before")
    @classmethod
    def strip_text(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("تاريخ النهاية قبل تاريخ البداية")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("مدة القرار لا تتجاوز سنة واحدة، سجّله على قرارين")
        return self
