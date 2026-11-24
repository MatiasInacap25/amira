from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amira_api.admin.audit_routes import router as audit_router
from amira_api.admin.badges import pending_badges
from amira_api.admin.deps import AdminUser, require_admin
from amira_api.admin.finance_routes import router as finance_router
from amira_api.admin.schemas import AdminIdentity
from amira_api.db import get_db_session

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
router.include_router(audit_router)
router.include_router(finance_router)


@router.get("/me")
def admin_me(admin: AdminUser) -> AdminIdentity:
    return AdminIdentity(user_id=admin.id, email=admin.email)


@router.get("/badges")
def admin_badges(session: Annotated[Session, Depends(get_db_session)]) -> dict[str, int]:
    return pending_badges(session)
