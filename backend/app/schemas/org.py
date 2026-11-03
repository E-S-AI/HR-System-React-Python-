from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrgUnitCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name_ar: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None
    governorate_code: str | None = None


class OrgUnitUpdate(BaseModel):
    name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class OrgUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_ar: str
    level_number: int
    governorate_code: str | None
    parent_id: int | None
    is_active: bool


class ScopeCreate(BaseModel):
    org_unit_id: int | None = None
    governorate_code: str | None = None
    include_sub_units: bool = True

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.org_unit_id is None) == (self.governorate_code is None):
            raise ValueError("حدد وحدة تنظيمية أو محافظة (واحداً فقط)")
        return self


class ScopeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    org_unit_id: int | None
    governorate_code: str | None
    include_sub_units: bool