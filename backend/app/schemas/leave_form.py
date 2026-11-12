from datetime import datetime

from pydantic import BaseModel


class LeaveFormUploadItem(BaseModel):
    leave_type_code: str
    name_ar: str
    page: int
    filename: str


class LeaveFormRead(BaseModel):
    code: str
    name_ar: str
    allow_employee_request: bool
    has_template: bool
    updated_at: datetime | None
