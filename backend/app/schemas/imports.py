from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportErrorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    column_name: str | None
    raw_value: str | None
    error_type: str
    error_message_ar: str


class ImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    module_name: str
    original_file_name: str
    sheet_name: str | None
    import_mode: str
    total_rows: int
    valid_new_rows: int
    valid_update_rows: int
    error_rows: int
    duplicate_rows: int
    status: str
    column_mapping: dict | None
    created_at: datetime
    committed_at: datetime | None


class ImportPreview(ImportJobRead):
    sample_errors: list[ImportErrorRead] = []