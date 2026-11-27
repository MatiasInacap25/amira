from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy.orm import Session

from amira_api.admin import people
from amira_api.admin.csv_export import EXPORT_LIMIT, export_csv
from amira_api.admin.deps import AdminUser
from amira_api.admin.listing import ListFilters, listed
from amira_api.db import get_db_session

router = APIRouter(prefix="/people")
Database = Annotated[Session, Depends(get_db_session)]
Resource = Literal["customers", "providers", "drivers", "invitations", "vehicles"]


class ModerationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(None, max_length=500)
    fields: dict | None = None


class EditFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    last_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    phone: Annotated[str, StringConstraints(pattern=r"^\+[1-9]\d{6,14}$", max_length=32)] | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)] | None = None
    description: str | None = Field(None, max_length=5000)
    commune_code: str | None = Field(None, pattern=r"^\d{5}$")
    brand: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    year: int | None = Field(None, ge=1886, le=2200)
    maximum_weight: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)


@router.get("/{resource}")
def list_people(resource: Resource, session: Database, params: Annotated[ListFilters, Query()]):
    return listed(session, people.QUERIES[resource](params), params)


@router.get("/{resource}/export.csv")
def download_people(resource: Resource, session: Database, params: Annotated[ListFilters, Query()]):
    source = people.QUERIES[resource](params)
    columns = list(source.selected_columns.keys())
    rows = listed(session, source, params, limit=EXPORT_LIMIT)
    return export_csv(resource, columns, ([row[key] for key in columns] for row in rows))


@router.get("/{resource}/{record_id}")
def person(resource: Resource, record_id: UUID, session: Database):
    return people.detail(session, resource, record_id)


@router.post("/{resource}/{record_id}/{action}")
def change_person(resource: Resource, record_id: UUID, action: str, payload: ModerationPayload, admin: AdminUser, session: Database):
    edit = None
    if action == "edit":
        try:
            edit = EditFields.model_validate(payload.fields or {}).model_dump(exclude_unset=True)
        except ValidationError as error:
            raise HTTPException(422, "Datos de edición no válidos.") from error
        if any(key in {"first_name", "last_name", "name", "brand", "model"} and value is None for key, value in edit.items()):
            raise HTTPException(422, "Los nombres y la descripción del vehículo no pueden estar vacíos.")
    people.moderate(session, admin.id, resource, record_id, action, payload.reason, edit)
    return {"status": "updated"}
