from uuid import UUID, uuid4

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from test_auth import FakeJwkClient, ISSUER, USER_ID, make_token

from amira_api import auth
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.settings import Settings, get_settings

OTHER_ID = "123e4567-e89b-12d3-a456-426614174099"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(auth, "PyJWKClient", FakeJwkClient)
    auth._jwks_client.cache_clear()
    engine = create_engine("sqlite://")
    app.dependency_overrides[get_settings] = lambda: Settings(supabase_jwt_issuer=ISSUER)
    app.dependency_overrides[get_db_session] = lambda: Session(engine)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        auth._jwks_client.cache_clear()
        engine.dispose()


def headers(**claims):
    return {"Authorization": f"Bearer {make_token(**claims)}"}


@pytest.mark.parametrize("path", ["/api/admin/me", "/api/admin/audit"])
def test_admin_routes_require_an_assured_allowlisted_subject(api, monkeypatch, path):
    assert api.get(path).status_code == 401
    non_admin = api.get(path, headers=headers())
    assert non_admin.status_code == 403
    assert non_admin.json() == {"detail": "Admin access required."}
    monkeypatch.setenv("ADMIN_USER_IDS", f" {OTHER_ID} , {USER_ID} ")
    assert api.get(path, headers=headers(aal="aal1")).status_code == 403


def test_admin_me_returns_token_identity(api, monkeypatch):
    monkeypatch.setenv("ADMIN_USER_IDS", f", {USER_ID} ,")
    result = api.get("/api/admin/me", headers=headers())
    assert result.status_code == 200
    assert result.json() == {"user_id": USER_ID, "email": "person@example.test"}


def test_allowlist_rejects_malformed_configuration(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_IDS", f"{USER_ID},invalid")
    with pytest.raises(RuntimeError, match="ADMIN_USER_IDS"):
        Settings()


def test_every_admin_route_declares_the_guard():
    from amira_api.admin.deps import require_admin

    routes = [route for route in iter_route_contexts(app.routes) if route.path.startswith("/api/admin/")]
    assert {route.path for route in routes} >= {"/api/admin/me", "/api/admin/audit", "/api/admin/audit/export.csv"}
    for route in routes:
        assert require_admin in {dependency.call for dependency in route.dependant.dependencies}, route.path


def test_audit_entry_participates_in_the_callers_transaction():
    from amira_api.admin.audit import append_audit
    from amira_api.models import AdminAuditLog

    engine = create_engine("sqlite://")
    AdminAuditLog.__table__.create(engine)
    with Session(engine) as session:
        entity_id = uuid4()
        append_audit(
            session, admin_user_id=UUID(USER_ID), action="rating.hide", entity_type="rating",
            entity_id=entity_id, reason="Moderation reason", before={"hidden": False}, after={"hidden": True},
        )
        event = session.scalar(select(AdminAuditLog))
        assert event is not None
        assert event.admin_user_id == UUID(USER_ID)
        assert event.entity_id == str(entity_id)
        assert event.reason == "Moderation reason"
        assert (event.before, event.after) == ({"hidden": False}, {"hidden": True})
        session.rollback()
        assert session.scalar(select(AdminAuditLog)) is None


def test_audit_listing_is_filtered_paginated_and_read_only(api, monkeypatch, tmp_path):
    from amira_api.admin.audit import append_audit
    from amira_api.models import AdminAuditLog

    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    AdminAuditLog.__table__.create(engine)
    with Session(engine) as session:
        for action in ("rating.hide", "rating.hide", "rating.show"):
            append_audit(session, admin_user_id=UUID(USER_ID), action=action, entity_type="rating", entity_id=uuid4())
        session.commit()
    def database():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db_session] = database
    monkeypatch.setenv("ADMIN_USER_IDS", USER_ID)
    response = api.get("/api/admin/audit", params={"action": "rating.hide", "limit": 1, "offset": 1}, headers=headers())
    assert response.status_code == 200
    result = response.json()
    assert (result["total"], result["limit"], result["offset"]) == (2, 1, 1)
    assert len(result["items"]) == 1
    assert result["items"][0]["action"] == "rating.hide"
    assert api.post("/api/admin/audit", headers=headers()).status_code == 405
    engine.dispose()
