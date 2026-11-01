"""Request and response models for the provider profile settings routes."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

DESCRIPTION_MAX_LENGTH = 2000
NAME_MAX_LENGTH = 160
SERVICE_TYPE_IDS_MAX_LENGTH = 50


class ProviderProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    commune_code: str | None = Field(default=None, max_length=5)
    service_type_ids: list[UUID] = Field(default_factory=list, max_length=SERVICE_TYPE_IDS_MAX_LENGTH)
    name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)

    @field_validator("description")
    @classmethod
    def _blank_description_is_absent(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
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
