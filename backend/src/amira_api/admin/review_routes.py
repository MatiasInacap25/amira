from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from amira_api.admin import review
from amira_api.admin.claim_service import resolve_claim
from amira_api.admin.csv_export import EXPORT_LIMIT, export_csv
from amira_api.admin.deps import AdminUser
from amira_api.admin.listing import ListFilters, listed
from amira_api.db import get_db_session
from amira_api.driver_verification_routes import get_driver_certificate_storage_resolver
from amira_api.evidence_storage import EvidenceStorage, get_evidence_storage_resolver
from amira_api.settings import Settings, get_settings

router = APIRouter(prefix="/review")
Resource = Literal["documents", "bank-accounts", "claims", "ratings"]
Database = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
CertificateStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_driver_certificate_storage_resolver)]
ServiceStorage = Annotated[Callable[[], EvidenceStorage], Depends(get_evidence_storage_resolver)]


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(None, max_length=500)


@router.get("/{resource}")
def list_reviews(resource: Resource, session: Database, params: Annotated[ListFilters, Query()]):
    return listed(session, review.QUERIES[resource](session, params), params)


@router.get("/{resource}/export.csv")
def download_reviews(resource: Resource, session: Database, params: Annotated[ListFilters, Query()]):
    source = review.QUERIES[resource](session, params)
    columns = list(source.selected_columns.keys())
    rows = listed(session, source, params, limit=EXPORT_LIMIT)
    return export_csv(resource, columns, ([row[key] for key in columns] for row in rows))


@router.get("/{resource}/{record_id}")
def item(resource: Resource, record_id: UUID, session: Database, settings: AppSettings,
         certificate_storage: CertificateStorage, service_storage: ServiceStorage, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return review.review_detail(session, resource, record_id, settings, certificate_storage, service_storage)


@router.post("/{resource}/{record_id}/{action}")
def decide(resource: Resource, record_id: UUID, action: str, payload: Decision, admin: AdminUser, session: Database, settings: AppSettings):
    if resource == "claims":
        if action not in {"resolve_customer", "resolve_provider"}:
            raise HTTPException(422, "Resolución no válida.")
        resolve_claim(session, record_id, admin.id, "customer" if action == "resolve_customer" else "provider", payload.reason, settings)
    else:
        review.review_action(session, resource, record_id, admin.id, action, payload.reason)
    return {"status": "updated"}
