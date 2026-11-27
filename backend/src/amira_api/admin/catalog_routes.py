from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy.orm import Session

from amira_api.admin import catalog
from amira_api.admin.csv_export import EXPORT_LIMIT, export_csv
from amira_api.admin.deps import AdminUser
from amira_api.admin.listing import ListFilters, listed
from amira_api.db import get_db_session

router = APIRouter(prefix="/catalog")
Database = Annotated[Session, Depends(get_db_session)]
Resource = Literal["service-types", "driver-types", "locations", "roles"]


class ServiceTypeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: str | None = Field(None, max_length=5000)


class CatalogChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: dict | None = None


@router.get("/{kind}")
def list_catalog(kind: Resource, session: Database, params: Annotated[ListFilters, Query()]):
    return listed(session, catalog.QUERIES[kind](params), params)


@router.get("/{kind}/export.csv")
def download(kind: Resource, session: Database, params: Annotated[ListFilters, Query()]):
    source = catalog.QUERIES[kind](params)
    columns = list(source.selected_columns.keys())
    return export_csv(kind, columns, ([row[key] for key in columns] for row in listed(session, source, params, limit=EXPORT_LIMIT)))


@router.get("/{kind}/{record_id}")
def read_catalog_item(kind: Resource, record_id: str, session: Database):
    return catalog.detail(session, kind, record_id)


@router.post("/service-types", status_code=201)
def create(payload: ServiceTypeInput, admin: AdminUser, session: Database):
    return {"id": catalog.create_service_type(session, admin.id, payload.model_dump())}


@router.post("/service-types/{record_id}/{action}")
def change(record_id: UUID, action: Literal["edit", "deactivate", "delete"], payload: CatalogChange, admin: AdminUser, session: Database):
    fields = None
    if action == "edit":
        try:
            fields = ServiceTypeInput.model_validate(payload.fields or {}).model_dump(exclude_unset=True)
        except ValidationError as error:
            raise HTTPException(422, "Datos de edición no válidos.") from error
    catalog.change_service_type(session, admin.id, record_id, action, fields)
    return {"status": "updated"}
