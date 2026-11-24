from fastapi import APIRouter, Depends

from amira_api.admin.audit_routes import router as audit_router
from amira_api.admin.deps import AdminUser, require_admin
from amira_api.admin.schemas import AdminIdentity

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
router.include_router(audit_router)


@router.get("/me")
def admin_me(admin: AdminUser) -> AdminIdentity:
    return AdminIdentity(user_id=admin.id, email=admin.email)
