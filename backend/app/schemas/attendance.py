from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.labels_ar import (
    ATTENDANCE_SOURCE_LABELS_AR,
    ATTENDANCE_STATUS_LABELS_AR,
    ATTENDANCE_SYNC_SOURCE_LABELS_AR,
    label_for,
)
from app.core.text import clean_text, to_ascii_digits


def _blank(v):
    return clean_text(v) if isinstance(v, str) else v


class BiometricDeviceCreate(BaseModel):
    device_name: str = Field(min_length=1, max_length=200)
    platform_url: str | None = Field(default=None, max_length=500)
    org_unit_id: int | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def normalize(self):
        self.device_name = (self.device_name or "").strip()
        return self


class BiometricDeviceUpdate(BaseModel):
    device_name: str | None = Field(default=None, min_length=1, max_length=200)
    platform_url: str | None = Field(default=None, max_length=500)
    org_unit_id: int | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def normalize(self):
        if self.device_name is not None:
            self.device_name = self.device_name.strip()
        return self


class BiometricDeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_name: str
    platform_url: str | None
    org_unit_id: int | None
    last_sync_at: datetime | None
    last_sync_status: str | None
    is_active: bool
    created_at: datetime


class AttendanceRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    biometric_user_id: str
    biometric_employee_name: str | None
    attendance_date: date
    first_in: time | None
    last_out: time | None
    platform_status: str | None
    platform_directorate: str | None
    work_schedule_id: int | None
    employee_id: int | None
    employee_name: str | None = None
    employee_code: str | None = None
    linked_leave_request_id: int | None
    late_minutes: int
    early_leave_minutes: int
    is_late_beyond_cutoff: bool
    is_early_leave_beyond_cutoff: bool
    counted_as_hourly_leave: bool
    hourly_leave_minutes_charged: int
    final_system_status: str | None
    final_system_status_label_ar: str | None = None
    source_type: str
    source_type_label_ar: str | None = None
    import_job_id: int | None
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    review_notes: str | None
    created_at: datetime

    @model_validator(mode="after")
    def fill_labels(self):
        self.final_system_status_label_ar = label_for(
            self.final_system_status, ATTENDANCE_STATUS_LABELS_AR
        )
        self.source_type_label_ar = label_for(self.source_type, ATTENDANCE_SOURCE_LABELS_AR)
        return self


class AttendanceSyncLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int | None
    sync_source: str
    sync_source_label_ar: str | None = None
    started_at: datetime
    finished_at: datetime | None
    records_fetched: int
    records_inserted: int
    records_duplicated: int
    unmapped_users_count: int
    error_details: str | None

    @model_validator(mode="after")
    def fill_labels(self):
        self.sync_source_label_ar = label_for(
            self.sync_source, ATTENDANCE_SYNC_SOURCE_LABELS_AR
        )
        return self


class AttendanceImportResult(BaseModel):
    import_job_id: int
    records_fetched: int
    records_inserted: int
    records_duplicated: int
    unmapped_users: list[dict]
    errors: list[dict]


class AttendanceManualCreate(BaseModel):
    biometric_user_id: str = Field(min_length=1, max_length=100)
    biometric_employee_name: str | None = Field(default=None, max_length=300)
    attendance_date: date
    first_in: time | None = None
    last_out: time | None = None
    platform_status: str | None = Field(default=None, max_length=100)
    platform_directorate: str | None = Field(default=None, max_length=300)
    employee_id: int | None = None

    @model_validator(mode="after")
    def normalize(self):
        self.biometric_user_id = to_ascii_digits(self.biometric_user_id.strip())
        self.biometric_employee_name = _blank(self.biometric_employee_name)
        self.platform_status = _blank(self.platform_status)
        self.platform_directorate = _blank(self.platform_directorate)
        if self.first_in is not None and self.last_out is not None:
            if self.last_out < self.first_in:
                raise ValueError("آخر خروج قبل أول دخول")
        return self


class AttendanceReview(BaseModel):
    review_notes: str | None = Field(default=None, max_length=1000)
    final_system_status: Literal[
        "PRESENT",
        "LATE",
        "EARLY_LEAVE",
        "LATE_AND_EARLY",
        "ON_LEAVE",
        "ON_MISSION",
        "OFFICIAL_HOLIDAY",
        "WEEKEND",
        "ABSENT",
        "MISSING_PUNCH",
    ]

    @model_validator(mode="after")
    def normalize(self):
        self.review_notes = _blank(self.review_notes)
        return self


class AttendanceReEvaluateResult(BaseModel):
    evaluated: int
    deductions_created: int
    deductions_removed: int
