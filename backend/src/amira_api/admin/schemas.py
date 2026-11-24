from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AdminIdentity(BaseModel):
    user_id: UUID
    email: str


class AdminAuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    admin_user_id: UUID
    action: str
    entity_type: str
    entity_id: str
    reason: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


class AdminPage[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
