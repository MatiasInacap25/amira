from uuid import UUID

import pytest
from claim_support import db  # noqa: F401
from test_provider_service_actions import fleet  # noqa: F401
from test_auth import USER_ID
from fastapi import HTTPException
from sqlalchemy import select

from amira_api.models import AdminAuditLog, Perfil, Usuario


def test_blocked_user_is_denied_without_deleting_account(db, fleet):
    from amira_api.admin.people import moderate
    from amira_api.auth import ensure_account_not_blocked

    AdminAuditLog.__table__.create(db.get_bind())
    user = db.scalar(select(Usuario).where(Usuario.id == fleet.service_a.form.customer_id))
    moderate(db, UUID(USER_ID), "customers", user.id, "block", "Suspended by moderation.")
    with pytest.raises(HTTPException) as denied:
        ensure_account_not_blocked(db, user.auth_user_id)
    assert denied.value.status_code == 403
    assert denied.value.detail == "Tu cuenta está bloqueada. Contacta a soporte."
    assert db.get(Usuario, user.id) is not None
    assert db.scalar(select(AdminAuditLog.action)) == "customer.block"
    with pytest.raises(HTTPException) as conflict:
        moderate(db, UUID(USER_ID), "customers", user.id, "block", "Repeated block attempt.")
    assert conflict.value.status_code == 409


def test_provider_suspension_preserves_existing_services(db, fleet):
    from amira_api.admin.people import moderate
    from amira_api.moderation import require_unsuspended_provider

    AdminAuditLog.__table__.create(db.get_bind())
    profile = db.get(Perfil, fleet.service_a.profile_id)
    previous = fleet.service_a.status
    moderate(db, UUID(USER_ID), "providers", profile.id, "suspend", "Suspension for moderation.")
    with pytest.raises(HTTPException) as denied:
        require_unsuspended_provider(db, profile.id)
    assert denied.value.status_code == 409
    assert denied.value.detail == "El perfil está suspendido."
    assert fleet.service_a.status == previous


def test_blocked_allowlisted_subject_can_reach_only_admin_routes(db, fleet):
    from fastapi.testclient import TestClient

    from amira_api.auth import AuthenticatedUser, get_verified_user
    from amira_api.clock import utc_now
    from amira_api.db import get_db_session
    from amira_api.main import app
    from amira_api.settings import Settings, get_settings

    user = db.get(Usuario, fleet.service_a.form.customer_id)
    user.blocked_at = utc_now()
    db.commit()
    identity = AuthenticatedUser(user.auth_user_id, user.email, UUID(USER_ID), "aal2", frozenset())
    app.dependency_overrides.update({
        get_verified_user: lambda: identity,
        get_db_session: lambda: db,
        get_settings: lambda: Settings(admin_user_ids={identity.id}),
    })
    try:
        with TestClient(app) as client:
            account = client.get("/api/account/me")
            assert account.status_code == 403
            assert account.json()["detail"] == "Tu cuenta está bloqueada. Contacta a soporte."
            admin = client.get("/api/admin/me")
            assert admin.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_customer_filter_and_contact_edit_preserve_identity(db, fleet):
    from amira_api.admin.listing import ListFilters, listed
    from amira_api.models import Reembolso
    from amira_api.admin.people import customers, detail, moderate

    AdminAuditLog.__table__.create(db.get_bind())
    Reembolso.__table__.create(db.get_bind())
    account = db.get(Usuario, fleet.service_a.form.customer_id)
    original_email = account.email
    params = ListFilters(q=original_email)
    page = listed(db, customers(params), params)
    assert [row["id"] for row in page["items"]] == [account.id]
    with pytest.raises(HTTPException, match="Acción o campos"):
        moderate(db, UUID(USER_ID), "customers", account.id, "edit", None, {"email": "different@example.test"})
    moderate(db, UUID(USER_ID), "customers", account.id, "edit", None, {"first_name": "Edited"})
    assert detail(db, "customers", account.id)["email"] == original_email
    assert db.scalar(select(AdminAuditLog.action)) == "customer.edit"


def test_provider_detail_exposes_related_records_and_open_count(db, fleet):
    from amira_api.admin.people import detail
    from amira_api.models import ServicioDisponible, Valoracion

    for model in (ServicioDisponible, Valoracion):
        model.__table__.create(db.get_bind())
    row = detail(db, "providers", fleet.service_a.profile_id)
    assert row["open_services"] >= 1
    assert row["driver_list"]
    assert row["vehicle_list"]
    assert row["rating_list"] == []
