from typing import Any
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from amira_api.models import AdminAuditLog


def append_audit(
    session: Session,
    *,
    admin_user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID | str,
    reason: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Stage one event without committing. Callers must pass only changed, non-secret fields."""
    session.add(AdminAuditLog(
        id=uuid4(), admin_user_id=admin_user_id, action=action, entity_type=entity_type,
        entity_id=str(entity_id), reason=reason, before=jsonable_encoder(before), after=jsonable_encoder(after),
    ))
