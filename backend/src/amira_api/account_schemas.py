"""Typed request and response contracts for authenticated account provisioning."""

from datetime import date
from enum import StrEnum
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


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
    national_id: str = Field(min_length=9, max_length=16)
    birth_date: date
    phone: str = Field(min_length=9, max_length=32)
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    company_tax_id: str | None = Field(default=None, min_length=1, max_length=16)
    commune_code: str | None = Field(default=None, pattern=r"^\d{5}$")
    also_driver: bool = False

    @staticmethod
    def normalize_rut(value: str) -> str:
        compact = re.sub(r"[.\s-]", "", value).upper()
        if not re.fullmatch(r"\d{7,8}[0-9K]", compact):
            raise PydanticCustomError("rut_invalid", "Ingresa un RUT chileno válido.")
        body, supplied_check_digit = compact[:-1], compact[-1]
        total = sum(int(digit) * weight for digit, weight in zip(reversed(body), (2, 3, 4, 5, 6, 7) * 2))
        remainder = 11 - (total % 11)
        expected_check_digit = "0" if remainder == 11 else "K" if remainder == 10 else str(remainder)
        if supplied_check_digit != expected_check_digit:
            raise PydanticCustomError("rut_invalid", "Ingresa un RUT chileno válido.")
        return f"{body}-{expected_check_digit}"

    @field_validator("national_id", "company_tax_id")
    @classmethod
    def validate_rut(cls, value: str | None) -> str | None:
        return cls.normalize_rut(value) if value is not None else None

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        if value > date.today() or value < date(1900, 1, 1):
            raise PydanticCustomError("birth_date_invalid", "Ingresa una fecha de nacimiento válida.")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = re.sub(r"[\s()-]", "", value)
        if not re.fullmatch(r"\+[1-9]\d{7,14}", normalized):
            raise PydanticCustomError("phone_invalid", "Ingresa un teléfono en formato internacional, por ejemplo +56912345678.")
        return normalized

    @model_validator(mode="after")
    def validate_role_fields(self):
        if self.role == AccountRole.CLIENT:
            if self.display_name is not None or self.company_tax_id is not None or self.also_driver or self.commune_code is not None:
                raise PydanticCustomError("client_provider_fields", "Las cuentas de cliente no pueden incluir datos de perfil de proveedor.")
        else:
            if self.display_name is None:
                raise PydanticCustomError("display_name_required", "Las cuentas de proveedor requieren un nombre público.")
            if self.commune_code is None:
                raise PydanticCustomError("commune_required", "Selecciona una comuna del catálogo para tu cuenta de proveedor.")
        if self.role == AccountRole.COMPANY_OWNER and self.company_tax_id is None:
            raise PydanticCustomError("company_tax_id_required", "Las cuentas de empresa requieren un RUT de empresa.")
        if self.role != AccountRole.COMPANY_OWNER and self.company_tax_id is not None:
            raise PydanticCustomError("company_tax_id_not_allowed", "Solo las cuentas de empresa pueden incluir un RUT de empresa.")
        if self.role != AccountRole.COMPANY_OWNER and self.also_driver:
            raise PydanticCustomError("linked_driver_not_allowed", "Solo las cuentas de empresa pueden habilitarse también como conductor vinculado.")
        return self


class AccountResponse(BaseModel):
    user_id: UUID
    role: AccountRoleCode
    profile_id: UUID | None = None
