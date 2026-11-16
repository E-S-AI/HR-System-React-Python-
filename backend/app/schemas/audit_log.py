from datetime import datetime
from pydantic import BaseModel, ConfigDict, model_validator

from app.core.labels_ar import AUDIT_ACTION_LABELS_AR, label_for


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    org_unit_id: int | None
    action_type: str
    action_type_label_ar: str | None = None
    target_table: str
    target_record_id: str | None
    old_data: dict | None
    new_data: dict | None
    ip_address: str | None
    created_at: datetime

    @model_validator(mode="after")
    def fill_label(self):
        self.action_type_label_ar = label_for(self.action_type, AUDIT_ACTION_LABELS_AR)
        return self