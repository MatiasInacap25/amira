"""Typed request and response contracts for authenticated account provisioning."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AccountRole(StrEnum):
    CLIENT = "client"
    COMPANY_OWNER = "company_owner"
    INDEPENDENT_DRIVER = "independent_driver"


class AccountRoleCode(StrEnum):
    CLIENT = "client"
    COMPANY_OWNER = "company_owner"
    COMPANY_DRIVER = "company_driver"
    INDEPENDENT_DRIVER = "independent_driver"


class AccountProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: AccountRole
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    company_tax_id: str | None = Field(default=None, min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_role_fields(self):
        if self.role == AccountRole.CLIENT:
            if self.display_name is not None or self.company_tax_id is not None:
                raise ValueError("Client accounts cannot include provider profile fields.")
        elif self.display_name is None:
            raise ValueError("Provider accounts require a public display name.")
        if self.role == AccountRole.COMPANY_OWNER and self.company_tax_id is None:
            raise ValueError("Company owner accounts require a company tax ID.")
        if self.role != AccountRole.COMPANY_OWNER and self.company_tax_id is not None:
            raise ValueError("Only company owners may include a company tax ID.")
        return self


class AccountResponse(BaseModel):
    user_id: UUID
    role: AccountRoleCode
    profile_id: UUID | None = None
