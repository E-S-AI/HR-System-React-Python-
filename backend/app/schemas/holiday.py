from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HolidayCreate(BaseModel):
    name_ar: str = Field(min_length=1, max_length=200)
    date_from: date
    date_to: date | None = None

    @model_validator(mode="after")
    def check_range(self):
        end = self.date_to or self.date_from
        if end < self.date_from:
            raise ValueError("تاريخ النهاية قبل تاريخ البداية")
        if (end - self.date_from).days > 30:
            raise ValueError("المدى الأقصى لإدخال واحد 31 يوماً")
        if not (2000 <= self.date_from.year <= 2100 and 2000 <= end.year <= 2100):
            raise ValueError("السنة خارج المدى المسموح")
        return self


class HolidayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    holiday_date: date
    name_ar: str


class HolidayCreateResult(BaseModel):
    created: list[HolidayRead]
    skipped_existing: list[date]
    affected_requests: list[int]