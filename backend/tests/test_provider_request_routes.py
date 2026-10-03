from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import Chat, ChatParticipante, FormularioServicio

AUTH_USER_ID = UUID("a6607c8d-9ea3-4166-8bf2-2333ae164d57")
PROVIDER_ACCOUNT_ID = UUID("59f7cf6f-4d38-4c9c-96e7-62f354874d1d")
CUSTOMER_ACCOUNT_ID = UUID("2a45e1d3-243f-4f24-8a4b-37c33f404e97")
PROFILE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e32")
OTHER_PROFILE_ID = UUID("4fab3c4d-8f5f-48ea-8ce2-c5187e8e97cd")
REQUEST_ID = UUID("fbdf8977-1abc-4be4-9bb8-a24ae3d24294")
SERVICE_TYPE_ID = UUID("6f6d0ae4-98ac-4a74-9a79-aac79443ed91")


class FakeResult:
    def __init__(self, *, row=None, scalar=None, rows=()):
        self.row = row
        self.scalar = scalar
        self.rows = list(rows)

    def mappings(self):
        return self

    def scalars(self):
        return self

    def one_or_none(self):
        return self.row

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar

    def all(self):
        return self.rows


class FakeStore:
    def __init__(self, *, role="company_owner", profile_id=PROFILE_ID, request_profile_id=PROFILE_ID):
        self.role = role
        self.profile_id = profile_id
        self.form = FormularioServicio(
            id=REQUEST_ID,
            profile_id=request_profile_id,
            service_type_id=SERVICE_TYPE_ID,
            origin="Santiago",
            destination="Valparaíso",
            requested_at=datetime(2026, 10, 12, 12, tzinfo=timezone.utc),
            status="pending",
            description="Traslado de muebles",
            customer_id=CUSTOMER_ACCOUNT_ID,
            is_exclusive=False,
            cargo_measurements="2 x 1 x 1 m",
        )
        self.forms = [self.form]
        self.chats: list[Chat] = []
        self.participants: list[ChatParticipante] = []
        self.lock = threading.Lock()
        self.statements = []


class FakeSession:
    def __init__(self, store: FakeStore, *, concurrent=False):
        self.store = store
        self.concurrent = concurrent
        self.statements = []
        self.added = []
        self.calls = 0
        self.lock_held = False
        self.original_status = None
        self.committed = False

    def execute(self, statement):
        self.store.statements.append(statement)
        self.statements.append(statement)
        self.calls += 1
        if self.calls == 1:
            return FakeResult(row=(PROVIDER_ACCOUNT_ID, self.store.role))
        if self.calls == 2:
            return FakeResult(scalar=self.store.profile_id)
        if getattr(statement, "_for_update_arg", None) is not None:
            if self.concurrent:
                self.store.lock.acquire()
                self.lock_held = True
            self.original_status = self.store.form.status
            if self.store.form.profile_id != self.store.profile_id:
                return FakeResult(scalar=None)
            return FakeResult(scalar=self.store.form)
        entity = statement.column_descriptions[0].get("entity") if statement.column_descriptions else None
        if entity is Chat:
            return FakeResult(rows=self.store.chats)
        sql = str(statement.compile(dialect=postgresql.dialect()))
        if "count(" in sql.lower():
            return FakeResult(scalar=sum(form.profile_id == self.store.profile_id for form in self.store.forms))
        if "Formulario_servicio" in sql:
            rows = []
            for form in self.store.forms:
                if form.profile_id == self.store.profile_id:
                    rows.append({
                        "request_id": form.id,
                        "status": form.status,
                        "origin": form.origin,
                        "destination": form.destination,
                        "requested_at": form.requested_at,
                        "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
                        "estimated_weight": None,
                        "estimated_volume": None,
                        "description": form.description,
                        "cargo_measurements": form.cargo_measurements,
                        "service_name": "Mudanzas",
                        "chat_id": None,
                    })
            return FakeResult(rows=rows)
        if "Chat." in sql or '"Chat"' in sql:
            return FakeResult(rows=[{"request_id": chat.form_id, "chat_id": chat.id} for chat in self.store.chats])
        return FakeResult(rows=[])

    def add(self, value):
        self.added.append(value)

    def add_all(self, values):
        self.added.extend(values)

    def flush(self):
        pass

    def commit(self):
        for value in self.added:
            if isinstance(value, Chat):
                self.store.chats.append(value)
            elif isinstance(value, ChatParticipante):
                self.store.participants.append(value)
        self.committed = True
        self._release_lock()

    def rollback(self):
        if self.original_status is not None:
            self.store.form.status = self.original_status
        self.added.clear()
        self._release_lock()

    def close(self):
        self._release_lock()

    def _release_lock(self):
        if self.lock_held:
            self.lock_held = False
            self.store.lock.release()


def provider_auth():
    return AuthenticatedUser(
        id=AUTH_USER_ID,
        email="provider@example.test",
        session_id=uuid4(),
        assurance="aal2",
        authentication_methods=frozenset({"password", "phone"}),
    )


def run_request(method: str, path: str, store: FakeStore, *, concurrent=False):
    app.dependency_overrides[get_db_session] = lambda: FakeSession(store, concurrent=concurrent)
    app.dependency_overrides[get_current_user] = provider_auth

    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path)

    try:
        return asyncio.run(send())
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


def _session_dependency(store: FakeStore, *, concurrent=False):
    session = FakeSession(store, concurrent=concurrent)
    try:
        yield session
    finally:
        session.close()


def test_provider_inbox_lists_only_owned_requests_and_excludes_customer_private_fields():
    store = FakeStore()
    store.forms.append(FormularioServicio(
        id=uuid4(), profile_id=OTHER_PROFILE_ID, service_type_id=SERVICE_TYPE_ID,
        origin="Other origin", destination="Other destination", status="pending",
        customer_id=uuid4(), is_exclusive=False,
    ))

    response = run_request("GET", "/api/provider/requests", store)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["requestId"] for item in body["items"]] == [str(REQUEST_ID)]
    assert body["items"][0]["serviceName"] == "Mudanzas"
    assert body["items"][0]["status"] == "pending"
    assert "customerId" not in response.text
    assert "email" not in response.text
    assert "nationalId" not in response.text


def test_only_company_owners_and_independent_provider_owners_can_open_inbox():
    client_store = FakeStore(role="client")
    response = run_request("GET", "/api/provider/requests", client_store)
    assert response.status_code == 403

    missing_profile = FakeStore(role="company_owner", profile_id=None)
    response = run_request("GET", "/api/provider/requests", missing_profile)
    assert response.status_code == 403

    independent_store = FakeStore(role="independent_driver")
    response = run_request("GET", "/api/provider/requests", independent_store)
    assert response.status_code == 200


def test_accept_creates_one_request_anchored_chat_and_two_participants():
    store = FakeStore()

    response = run_request("POST", f"/api/provider/requests/{REQUEST_ID}/accept", store)

    assert response.status_code == 200
    body = response.json()
    assert body == {"requestId": str(REQUEST_ID), "status": "accepted", "chatId": str(store.chats[0].id)}
    assert store.form.status == "accepted"
    assert len(store.chats) == 1
    assert store.chats[0].form_id == REQUEST_ID
    assert {participant.user_id for participant in store.participants} == {CUSTOMER_ACCOUNT_ID, PROVIDER_ACCOUNT_ID}
    assert {participant.chat_id for participant in store.participants} == {store.chats[0].id}
    assert not any(isinstance(value, Chat) and value.form_id != REQUEST_ID for value in store.chats)


def test_repeated_accept_is_idempotent_and_does_not_duplicate_chat_or_participants():
    store = FakeStore()
    first = run_request("POST", f"/api/provider/requests/{REQUEST_ID}/accept", store)
    replay = run_request("POST", f"/api/provider/requests/{REQUEST_ID}/accept", store)

    assert first.status_code == replay.status_code == 200
    assert first.json()["chatId"] == replay.json()["chatId"]
    assert len(store.chats) == 1
    assert len(store.participants) == 2


def test_reject_is_idempotent_and_never_creates_chat_or_memberships():
    store = FakeStore()
    first = run_request("POST", f"/api/provider/requests/{REQUEST_ID}/reject", store)
    replay = run_request("POST", f"/api/provider/requests/{REQUEST_ID}/reject", store)

    assert first.status_code == replay.status_code == 200
    assert replay.json() == {"requestId": str(REQUEST_ID), "status": "rejected", "chatId": None}
    assert store.form.status == "rejected"
    assert store.chats == []
    assert store.participants == []


def test_conflicting_decision_and_cross_profile_request_fail_without_changing_state():
    store = FakeStore()
    accepted = run_request("POST", f"/api/provider/requests/{REQUEST_ID}/accept", store)
    assert accepted.status_code == 200
    conflict = run_request("POST", f"/api/provider/requests/{REQUEST_ID}/reject", store)
    assert conflict.status_code == 409
    assert store.form.status == "accepted"
    assert len(store.chats) == 1

    other_provider = FakeStore(profile_id=OTHER_PROFILE_ID)
    hidden = run_request("POST", f"/api/provider/requests/{REQUEST_ID}/accept", other_provider)
    assert hidden.status_code == 404
    assert other_provider.form.status == "pending"
    assert other_provider.chats == []


def test_accept_and_reject_race_cannot_both_win_or_duplicate_chat():
    store = FakeStore()
    app.dependency_overrides[get_db_session] = lambda: FakeSession(store, concurrent=True)
    app.dependency_overrides[get_current_user] = provider_auth

    async def send_both():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await asyncio.gather(
                client.post(f"/api/provider/requests/{REQUEST_ID}/accept"),
                client.post(f"/api/provider/requests/{REQUEST_ID}/reject"),
            )

    try:
        responses = asyncio.run(send_both())
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert store.form.status in {"accepted", "rejected"}
    if store.form.status == "accepted":
        assert len(store.chats) == 1
        assert len(store.participants) == 2
    else:
        assert store.chats == []
        assert store.participants == []


def test_request_decision_query_uses_postgres_row_lock():
    store = FakeStore()
    response = run_request("POST", f"/api/provider/requests/{REQUEST_ID}/accept", store)
    assert response.status_code == 200
    decision_query = next(statement for statement in store.statements if getattr(statement, "_for_update_arg", None) is not None)
    assert "FOR UPDATE" in str(decision_query.compile(dialect=postgresql.dialect()))
