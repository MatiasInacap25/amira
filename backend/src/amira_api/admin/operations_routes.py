from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from amira_api.admin import operations
from amira_api.admin.csv_export import EXPORT_LIMIT, export_csv
from amira_api.admin.deps import AdminUser
from amira_api.admin.listing import ListFilters, listed
from amira_api.db import get_db_session
from amira_api.evidence_storage import (
    EvidenceStorage, get_chat_attachment_storage_resolver, get_evidence_storage_resolver, get_request_image_storage_resolver,
)
from amira_api.settings import Settings, get_settings

router = APIRouter(prefix="/operations")
Resource = Literal["requests", "quotations", "services", "chats", "trips"]
Database = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
RequestStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_request_image_storage_resolver)]
ServiceStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_evidence_storage_resolver)]
AttachmentStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_chat_attachment_storage_resolver)]


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(None, max_length=500)


class ChatAccess(Decision):
    before: UUID | None = None


@router.get("/{resource}")
def list_operations(resource: Resource, session: Database, settings: AppSettings, params: Annotated[ListFilters, Query()]):
    data = listed(session, operations.QUERIES[resource](session, params), params)
    if resource == "quotations":
        data["items"] = [operations.breakdown(row, settings) for row in data["items"]]
    return data


@router.get("/{resource}/export.csv")
def download(resource: Resource, session: Database, settings: AppSettings, params: Annotated[ListFilters, Query()]):
    source = operations.QUERIES[resource](session, params)
    columns = list(source.selected_columns.keys())
    rows = listed(session, source, params, limit=EXPORT_LIMIT)
    if resource == "quotations":
        columns.extend(("net", "iva", "commission"))
        rows = [operations.breakdown(row, settings) for row in rows]
    return export_csv(resource, columns, ([row.get(key) for key in columns] for row in rows))


@router.get("/{resource}/{record_id}")
def item(resource: Resource, record_id: UUID, session: Database, settings: AppSettings,
         request_storage: RequestStorage, service_storage: ServiceStorage, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return operations.detail(session, resource, record_id, settings, request_storage, service_storage)


@router.post("/chats/{record_id}/transcript")
def open_transcript(record_id: UUID, payload: ChatAccess, admin: AdminUser, session: Database,
                    attachments: AttachmentStorage, settings: AppSettings, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return operations.transcript(session, record_id, admin.id, payload.reason, payload.before, attachments, settings)


@router.post("/{resource}/{record_id}/{action}")
def decide(resource: Resource, record_id: UUID, action: str, payload: Decision, admin: AdminUser,
           session: Database, settings: AppSettings):
    if resource == "services" and action == "cancel":
        operations.cancel_admin_service(session, record_id, admin.id, payload.reason, settings)
    elif resource == "trips" and action in {"unpublish", "close"}:
        operations.change_trip(session, record_id, admin.id, action, payload.reason)
    else:
        raise HTTPException(422, "Acción no válida para el registro.")
    return {"status": "updated"}
