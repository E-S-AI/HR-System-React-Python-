from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.labels_ar import IMPORT_ERROR_TYPE_LABELS_AR, IMPORT_STATUS_LABELS_AR, label_for


class ImportErrorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    column_name: str | None
    raw_value: str | None
    error_type: str
    error_type_label_ar: str | None = None
    error_message_ar: str

    @model_validator(mode="after")
    def fill_label(self):
        self.error_type_label_ar = label_for(self.error_type, IMPORT_ERROR_TYPE_LABELS_AR)
        return self


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
    status_label_ar: str | None = None
    column_mapping: dict | None
    created_at: datetime
    committed_at: datetime | None

    @model_validator(mode="after")
    def fill_label(self):
        self.status_label_ar = label_for(self.status, IMPORT_STATUS_LABELS_AR)
        return self


class ImportPreview(ImportJobRead):
    sample_errors: list[ImportErrorRead] = []