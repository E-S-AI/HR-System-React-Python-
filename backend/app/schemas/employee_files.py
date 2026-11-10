from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _blank(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class QualificationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qualification_level: str | None = Field(default=None, max_length=100)
    specialization: str | None = Field(default=None, max_length=150)
    issuing_institution: str | None = Field(default=None, max_length=150)
    graduation_year: str | None = Field(default=None, max_length=20)
    is_hiring_qualification: bool | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("*", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        return _blank(v)


class TrainingPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_name: str | None = Field(default=None, max_length=200)
    training_provider: str | None = Field(default=None, max_length=150)
    course_date: str | None = Field(default=None, max_length=50)
    duration_text: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("*", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        return _blank(v)


class AssignmentInput(BaseModel):
    """بدء تكليف أو تجديده."""

    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date | None = None
    duration_text: str | None = Field(default=None, max_length=100)
    assigned_position_or_unit: str | None = Field(default=None, max_length=200)
    decision_number: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator(
        "duration_text", "assigned_position_or_unit", "decision_number", "notes",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, v):
        return _blank(v)

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("تاريخ الانتهاء قبل تاريخ البدء")
        return self


class AssignmentEnd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    end_date: date
    decision_number: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("decision_number", "notes", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        return _blank(v)


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    sequence_number: int
    action_type: str
    start_date: date
    end_date: date | None
    duration_text: str | None
    assigned_position_or_unit: str | None
    decision_number: str | None
    is_current: bool
    notes: str | None
    created_by_hr_id: int
    created_at: datetime