"""Request and response models for the provider profile settings routes."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DESCRIPTION_MAX_LENGTH = 2000
NAME_MAX_LENGTH = 160
SERVICE_TYPE_IDS_MAX_LENGTH = 50
# Chilean commune codes (Comunas.Codigo) are exactly 5 digits; models.py enforces the same format in ck_commune_code_format.
COMMUNE_CODE_LENGTH = 5
COMMUNE_CODE_PATTERN = r"^[0-9]{5}$"


class ProviderProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # description, commune_code and service_type_ids have no defaults: an omitted field is a 422, never an implicit clear.
    # Explicit null (description, commune_code) and [] (service_type_ids) remain valid draft saves.
    description: str | None = Field(max_length=DESCRIPTION_MAX_LENGTH)
    commune_code: str | None = Field(
        max_length=COMMUNE_CODE_LENGTH,
        pattern=COMMUNE_CODE_PATTERN,
    )
    service_type_ids: list[UUID] = Field(max_length=SERVICE_TYPE_IDS_MAX_LENGTH)
    name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)

    # mode="before" strips first, so the length bounds in Field measure the stored text, not the padded input.
    @field_validator("description", mode="before")
    @classmethod
    def _blank_description_is_absent(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        return value.strip() or None

    @field_validator("name", mode="before")
    @classmethod
    def _name_must_not_be_blank(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class ProviderProfileView(BaseModel):
    name: str
    kind: Literal["company", "independent_driver"]
    description: str | None
    commune_code: str | None
    service_type_ids: list[UUID]
    published: bool
    missing: list[Literal["description", "commune", "service_types"]]
