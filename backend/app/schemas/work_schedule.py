from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkScheduleCreate(BaseModel):
    schedule_name_ar: str = Field(min_length=1, max_length=150)
    official_start_time: time = time(8, 0)
    official_end_time: time = time(15, 0)
    late_grace_minutes: int = Field(20, ge=0, le=120)
    early_leave_grace_minutes: int = Field(20, ge=0, le=120)
    effective_from_date: date
    effective_to_date: date | None = None

    @model_validator(mode="after")
    def check_times(self):
        if self.official_end_time <= self.official_start_time:
            raise ValueError("وقت الانتهاء يجب أن يكون بعد وقت البدء")
        if self.effective_to_date and self.effective_to_date < self.effective_from_date:
            raise ValueError("تاريخ النهاية قبل تاريخ البدء")
        return self


class WorkScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_name_ar: str
    official_start_time: time
    official_end_time: time
    late_grace_minutes: int
    early_leave_grace_minutes: int
    late_cutoff_time: time
    early_leave_cutoff_time: time
    workday_minutes: int
    effective_from_date: date
    effective_to_date: date | None
    updated_by_user_id: int | None
    updated_at: datetime