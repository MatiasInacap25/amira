from uuid import UUID, uuid4

import pytest
from claim_support import db  # noqa: F401
from fastapi import HTTPException
from sqlalchemy import select
from test_auth import USER_ID
from test_provider_service_actions import fleet  # noqa: F401

from amira_api.models import AdminAuditLog, ServicioDisponible, TipoServicio


def test_service_type_can_be_created_edited_deactivated_and_deleted(db):
    from amira_api.admin.catalog import change_service_type, create_service_type
    from amira_api.service_type_visibility import visible_service_type_clause

    for model in (AdminAuditLog, ServicioDisponible):
        model.__table__.create(db.get_bind())
    actor = UUID(USER_ID)
    identifier = create_service_type(db, actor, {"name": "Envío Local", "description": "Solo dentro de la comuna."})
    assert db.get(TipoServicio, identifier).slug == "envio-local"
    change_service_type(db, actor, identifier, "edit", {"name": "Envío regional"})
    assert db.get(TipoServicio, identifier).slug == "envio-local"
    change_service_type(db, actor, identifier, "deactivate")
    assert db.scalar(select(TipoServicio.id).where(TipoServicio.id == identifier, visible_service_type_clause())) is None
    change_service_type(db, actor, identifier, "delete")
    assert db.get(TipoServicio, identifier) is None
    assert set(db.scalars(select(AdminAuditLog.action))) == {
        "service_type.create", "service_type.edit", "service_type.deactivate", "service_type.delete",
    }


def test_referenced_type_can_be_hidden_but_not_deleted(db, fleet):
    from amira_api.admin.catalog import change_service_type

    for model in (AdminAuditLog, ServicioDisponible):
        model.__table__.create(db.get_bind())
    identifier = fleet.service_a.form.service_type_id
    with pytest.raises(HTTPException) as refused:
        change_service_type(db, UUID(USER_ID), identifier, "delete")
    assert refused.value.status_code == 409
    assert db.get(TipoServicio, identifier) is not None
    assert db.scalar(select(AdminAuditLog.id)) is None
    change_service_type(db, UUID(USER_ID), identifier, "deactivate")
    assert db.get(TipoServicio, identifier).deactivated_at is not None


@pytest.mark.parametrize("endpoint", ["profile", "request"])
def test_deactivation_removes_provider_type_from_new_quote_selection(db, fleet, monkeypatch, endpoint):
    from fastapi.testclient import TestClient

    from amira_api.admin.catalog import change_service_type
    from amira_api.auth import AuthenticatedUser, get_current_user
    from amira_api.clock import utc_now
    from amira_api.db import get_db_session
    from amira_api.main import app
    from amira_api.models import RolPerfil

    from test_provider_service_actions import CUSTOMER_AUTH
    from test_public_provider_routes import LEGACY_QUOTE_BODY

    for model in (AdminAuditLog, RolPerfil, ServicioDisponible):
        model.__table__.create(db.get_bind())
    provider = fleet.company
    identifier = fleet.service_a.form.service_type_id
    provider.public_activated_at = utc_now()
    offering_id = uuid4()
    db.add_all([
        RolPerfil(id=provider.role_id, name="Company", code="company"),
        ServicioDisponible(id=offering_id, profile_id=provider.id, service_type_id=identifier),
    ])
    db.commit()
    monkeypatch.setitem(app.dependency_overrides, get_db_session, lambda: db)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: AuthenticatedUser(
        id=CUSTOMER_AUTH, email="casey@example.test", session_id=uuid4(), assurance="aal2",
        authentication_methods=frozenset({"password", "phone"}),
    ))
    client = TestClient(app)
    profile_url = f"/api/providers/{provider.id}"
    payload = {**LEGACY_QUOTE_BODY, "profileId": str(provider.id), "serviceTypeId": str(identifier)}
    if endpoint == "profile":
        assert [entry["serviceTypeId"] for entry in client.get(profile_url).json()["services"]] == [str(identifier)]
    else:
        assert client.post("/api/service-requests", json=payload).status_code == 201

    change_service_type(db, UUID(USER_ID), identifier, "deactivate")

    if endpoint == "profile":
        response = client.get(profile_url)
        assert response.status_code == 200
        assert response.json()["services"] == []
    else:
        response = client.post("/api/service-requests", json=payload)
        assert response.status_code == 404
    assert db.get(ServicioDisponible, offering_id).service_type_id == identifier
    assert fleet.service_a.form.service_type_id == identifier
