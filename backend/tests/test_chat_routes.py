"""Chat list and chat message routes, exercised against in-memory SQLite with the real ORM queries.

Postgres-only CHECK constraints (regex `~`) are not emitted for the two lookup tables, which are created
with plain DDL. Everything else comes from the ORM metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import (
    Base,
    Chat,
    ChatParticipante,
    Commune,
    FormularioServicio,
    Mensaje,
    Perfil,
    TipoServicio,
    Usuario,
)

CUSTOMER_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e01")
PROVIDER_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e02")
DRIVER_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e03")
OTHER_CUSTOMER_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e04")
UNKNOWN_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e05")

SECRET_CONTACT_VALUES = ("+56911112222", "+56922223333", "casey.customer@example.test", "12345678-5", "pat@example.test")


def _register_btrim(connection, _record) -> None:
    # The unique email index is an expression over btrim(), which SQLite does not provide.
    connection.create_function("btrim", 1, lambda value: value.strip() if value else value, deterministic=True)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _register_btrim)
    tables = ("Usuario", "Perfil", "Formulario_servicio", "Chat", "Chat_participantes", "Mensajes")
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in tables])
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE "Comunas" ("Codigo" VARCHAR(5) PRIMARY KEY, "Codigo_Region" VARCHAR(2) NOT NULL, "Nombre" VARCHAR(120) NOT NULL)'
        ))
        connection.execute(text(
            'CREATE TABLE "Tipos_Servicio" ("ID" CHAR(32) PRIMARY KEY, "Nombre_servicio" VARCHAR(120) NOT NULL, "Slug" VARCHAR(120) NOT NULL)'
        ))
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def api(db):
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app)

    def get(path: str, *, as_auth_id: UUID):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=as_auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
        return client.get(path)

    yield get
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@dataclass
class Scenario:
    customer: Usuario
    provider_owner: Usuario
    driver_owner: Usuario
    other_customer: Usuario
    provider_profile: Perfil
    driver_profile: Perfil
    chat_a: Chat  # customer <-> provider; last message from the provider
    chat_b: Chat  # other customer <-> provider; no messages
    chat_c: Chat  # customer <-> driver; no messages
    chat_d: Chat  # other customer <-> driver; no messages


def _user(db: Session, *, auth_id: UUID, first: str, last: str, email: str, phone: str | None = None, rut: str | None = None) -> Usuario:
    row = Usuario(
        id=uuid4(),
        auth_user_id=auth_id,
        first_name=first,
        last_name=last,
        email=email,
        phone=phone,
        national_id=rut,
        role_id=uuid4(),
    )
    db.add(row)
    return row


def _profile(db: Session, *, owner: Usuario, name: str, kind: str) -> Perfil:
    row = Perfil(id=uuid4(), owner_user_id=owner.id, name=name, kind=kind, role_id=uuid4())
    db.add(row)
    return row


def _chat(db: Session, *, customer: Usuario, profile: Perfil, service: TipoServicio, origin: Commune | None,
          destination: Commune | None, created_at: datetime, provider_owner: Usuario) -> Chat:
    form = FormularioServicio(
        id=uuid4(),
        profile_id=profile.id,
        service_type_id=service.id,
        origin_commune_code=origin.code if origin else None,
        destination_commune_code=destination.code if destination else None,
        status="accepted",
        customer_id=customer.id,
        is_exclusive=False,
        created_at=created_at,
    )
    chat = Chat(id=uuid4(), form_id=form.id, created_at=created_at)
    db.add_all([form, chat])
    db.flush()
    db.add_all([
        ChatParticipante(id=uuid4(), user_id=customer.id, chat_id=chat.id),
        ChatParticipante(id=uuid4(), user_id=provider_owner.id, chat_id=chat.id),
    ])
    return chat


@pytest.fixture
def scenario(db: Session) -> Scenario:
    customer = _user(db, auth_id=CUSTOMER_AUTH, first="Casey", last="Customer",
                     email="casey.customer@example.test", phone="+56911112222", rut="12345678-5")
    provider_owner = _user(db, auth_id=PROVIDER_AUTH, first="Pat", last="Provider",
                           email="pat@example.test", phone="+56922223333")
    driver_owner = _user(db, auth_id=DRIVER_AUTH, first="Dana", last="Driver", email="dana@example.test")
    other_customer = _user(db, auth_id=OTHER_CUSTOMER_AUTH, first="Xavi", last="Other", email="xavi@example.test")
    provider_profile = _profile(db, owner=provider_owner, name="Transportes Norte", kind="company")
    driver_profile = _profile(db, owner=driver_owner, name="Dana Driver Fletes", kind="independent_driver")
    mudanzas = TipoServicio(id=uuid4(), name="Mudanzas", slug="mudanzas")
    fletes = TipoServicio(id=uuid4(), name="Fletes", slug="fletes")
    santiago = Commune(code="13101", region_code="13", name="Santiago")
    valparaiso = Commune(code="05101", region_code="05", name="Valparaíso")
    db.add_all([mudanzas, fletes, santiago, valparaiso])
    db.flush()

    chat_a = _chat(db, customer=customer, profile=provider_profile, service=mudanzas, origin=santiago,
                   destination=valparaiso, created_at=datetime(2026, 10, 1, 10, tzinfo=timezone.utc),
                   provider_owner=provider_owner)
    chat_b = _chat(db, customer=other_customer, profile=provider_profile, service=mudanzas, origin=santiago,
                   destination=None, created_at=datetime(2026, 10, 2, 9, tzinfo=timezone.utc),
                   provider_owner=provider_owner)
    chat_c = _chat(db, customer=customer, profile=driver_profile, service=fletes, origin=santiago,
                   destination=None, created_at=datetime(2026, 10, 3, 8, tzinfo=timezone.utc),
                   provider_owner=driver_owner)
    chat_d = _chat(db, customer=other_customer, profile=driver_profile, service=fletes, origin=None,
                   destination=None, created_at=datetime(2026, 10, 4, 8, tzinfo=timezone.utc),
                   provider_owner=driver_owner)
    db.flush()
    db.add_all([
        Mensaje(id=uuid4(), chat_id=chat_a.id, user_id=customer.id, content="Hola, ¿a qué hora llegan?",
                created_at=datetime(2026, 10, 1, 10, 5, tzinfo=timezone.utc)),
        Mensaje(id=uuid4(), chat_id=chat_a.id, user_id=provider_owner.id, content="x" * 200,
                created_at=datetime(2026, 10, 1, 11, tzinfo=timezone.utc)),
    ])
    db.commit()
    return Scenario(
        customer=customer,
        provider_owner=provider_owner,
        driver_owner=driver_owner,
        other_customer=other_customer,
        provider_profile=provider_profile,
        driver_profile=driver_profile,
        chat_a=chat_a,
        chat_b=chat_b,
        chat_c=chat_c,
        chat_d=chat_d,
    )


def test_chat_list_contains_only_caller_chats_ordered_by_last_activity(api, scenario):
    response = api("/api/chats", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    body = response.json()
    # chat_c was created on 10-03; chat_a's last activity is the provider's 10-01 11:00 message.
    assert [item["chatId"] for item in body["items"]] == [str(scenario.chat_c.id), str(scenario.chat_a.id)]
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_customer_counterpart_is_provider_public_name_and_kind(api, scenario):
    items = {item["chatId"]: item for item in api("/api/chats", as_auth_id=CUSTOMER_AUTH).json()["items"]}

    company_chat = items[str(scenario.chat_a.id)]
    assert company_chat["counterpart"] == {
        "name": "Transportes Norte",
        "kind": "company",
        "providerProfileId": str(scenario.provider_profile.id),
    }
    assert company_chat["serviceName"] == "Mudanzas"
    assert company_chat["originCommuneName"] == "Santiago"
    assert company_chat["destinationCommuneName"] == "Valparaíso"
    assert company_chat["requestId"] is not None
    assert company_chat["createdAt"].startswith("2026-10-01")

    driver_chat = items[str(scenario.chat_c.id)]
    assert driver_chat["counterpart"] == {
        "name": "Dana Driver Fletes",
        "kind": "independent_driver",
        "providerProfileId": str(scenario.driver_profile.id),
    }
    assert driver_chat["destinationCommuneName"] is None


def test_provider_counterpart_is_customer_full_name_without_profile_id(api, scenario):
    items = {item["chatId"]: item for item in api("/api/chats", as_auth_id=PROVIDER_AUTH).json()["items"]}

    assert set(items) == {str(scenario.chat_b.id), str(scenario.chat_a.id)}
    assert items[str(scenario.chat_a.id)]["counterpart"] == {
        "name": "Casey Customer",
        "kind": "customer",
        "providerProfileId": None,
    }
    assert items[str(scenario.chat_b.id)]["counterpart"]["name"] == "Xavi Other"


def test_last_message_is_truncated_and_marks_whether_caller_sent_it(api, scenario):
    provider_view = {item["chatId"]: item for item in api("/api/chats", as_auth_id=PROVIDER_AUTH).json()["items"]}
    customer_view = {item["chatId"]: item for item in api("/api/chats", as_auth_id=CUSTOMER_AUTH).json()["items"]}

    provider_last = provider_view[str(scenario.chat_a.id)]["lastMessage"]
    assert provider_last["content"] == "x" * 140
    assert provider_last["fromMe"] is True
    assert provider_last["sentAt"].startswith("2026-10-01T11:00")

    customer_last = customer_view[str(scenario.chat_a.id)]["lastMessage"]
    assert customer_last["fromMe"] is False
    assert provider_view[str(scenario.chat_b.id)]["lastMessage"] is None


def test_chat_without_messages_is_ordered_by_creation_and_has_null_last_message(api, scenario):
    items = api("/api/chats", as_auth_id=PROVIDER_AUTH).json()["items"]

    # chat_b (created 10-02) sorts ahead of chat_a (last message 10-01 11:00).
    assert [item["chatId"] for item in items] == [str(scenario.chat_b.id), str(scenario.chat_a.id)]
    assert items[0]["lastMessage"] is None


def test_chat_list_never_exposes_contact_or_auth_details(api, scenario):
    for auth_id in (CUSTOMER_AUTH, PROVIDER_AUTH, DRIVER_AUTH):
        response = api("/api/chats", as_auth_id=auth_id)
        assert response.status_code == 200
        text_body = response.text
        for value in SECRET_CONTACT_VALUES:
            assert value not in text_body
        assert str(scenario.customer.auth_user_id) not in text_body
        assert str(scenario.provider_owner.auth_user_id) not in text_body
        assert "email" not in text_body.lower()
        assert "phone" not in text_body.lower()


def test_total_and_items_come_from_the_same_filtered_relation(api, scenario):
    first = api("/api/chats?limit=1&offset=0", as_auth_id=CUSTOMER_AUTH).json()
    second = api("/api/chats?limit=1&offset=1", as_auth_id=CUSTOMER_AUTH).json()

    assert first["total"] == second["total"] == 2
    assert [item["chatId"] for item in first["items"]] == [str(scenario.chat_c.id)]
    assert [item["chatId"] for item in second["items"]] == [str(scenario.chat_a.id)]


def test_caller_without_chats_or_account_gets_an_empty_page(api, scenario):
    unknown = api("/api/chats", as_auth_id=UNKNOWN_AUTH).json()
    assert unknown == {"items": [], "total": 0, "limit": 20, "offset": 0}


@pytest.mark.parametrize("query", ["limit=0", "limit=51", "offset=-1", "offset=5001"])
def test_page_bounds_are_validated(api, scenario, query):
    assert api(f"/api/chats?{query}", as_auth_id=CUSTOMER_AUTH).status_code == 422


def _messages_path(chat_id: UUID, query: str = "") -> str:
    return f"/api/chats/{chat_id}/messages{query}"


def _add_customer_messages(db: Session, scenario: Scenario, timestamps: list[datetime]) -> None:
    db.add_all([
        Mensaje(id=uuid4(), chat_id=scenario.chat_a.id, user_id=scenario.customer.id, content=f"extra {index}",
                created_at=stamp)
        for index, stamp in enumerate(timestamps)
    ])
    db.commit()


def test_participant_gets_header_and_all_messages_oldest_to_newest(api, scenario):
    response = api(_messages_path(scenario.chat_a.id), as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["chatId"] == str(scenario.chat_a.id)
    assert body["serviceName"] == "Mudanzas"
    assert body["counterpart"] == {
        "name": "Transportes Norte",
        "kind": "company",
        "providerProfileId": str(scenario.provider_profile.id),
    }
    assert "lastMessage" not in body
    assert body["hasMore"] is False
    assert [message["content"] for message in body["messages"]] == ["Hola, ¿a qué hora llegan?", "x" * 200]
    assert body["messages"][0]["messageId"] is not None
    assert body["messages"][0]["sentAt"].startswith("2026-10-01T10:05")


def test_messages_are_marked_from_me_with_sender_names_per_side(api, scenario):
    customer_view = api(_messages_path(scenario.chat_a.id), as_auth_id=CUSTOMER_AUTH).json()["messages"]
    provider_view = api(_messages_path(scenario.chat_a.id), as_auth_id=PROVIDER_AUTH).json()["messages"]

    assert [message["fromMe"] for message in customer_view] == [True, False]
    assert [message["fromMe"] for message in provider_view] == [False, True]
    # A customer sees the provider's public name, never the owner's personal name.
    assert customer_view[1]["senderName"] == "Transportes Norte"
    assert customer_view[0]["senderName"] == "Casey Customer"
    assert provider_view[0]["senderName"] == "Casey Customer"
    assert provider_view[1]["senderName"] == "Pat Provider"


def test_chat_with_no_messages_returns_empty_list(api, scenario):
    body = api(_messages_path(scenario.chat_b.id), as_auth_id=PROVIDER_AUTH).json()

    assert body["messages"] == []
    assert body["hasMore"] is False


def test_non_participant_and_unknown_chat_both_return_the_same_not_found(api, scenario):
    # Positive control: the same chat is readable by its participant, so the 404s below are not a missing route.
    assert api(_messages_path(scenario.chat_c.id), as_auth_id=CUSTOMER_AUTH).status_code == 200
    other = api(_messages_path(scenario.chat_c.id), as_auth_id=OTHER_CUSTOMER_AUTH)
    provider_outsider = api(_messages_path(scenario.chat_c.id), as_auth_id=PROVIDER_AUTH)
    unknown = api(_messages_path(uuid4()), as_auth_id=CUSTOMER_AUTH)

    assert other.status_code == provider_outsider.status_code == unknown.status_code == 404
    assert other.json() == unknown.json() == provider_outsider.json()


def test_unknown_account_gets_not_found(api, scenario):
    assert api(_messages_path(scenario.chat_a.id), as_auth_id=CUSTOMER_AUTH).status_code == 200
    assert api(_messages_path(scenario.chat_a.id), as_auth_id=UNKNOWN_AUTH).status_code == 404


def test_cursor_pagination_walks_every_message_once_newest_page_first(api, scenario, db):
    _add_customer_messages(db, scenario, [
        datetime(2026, 10, 1, 11, 10, tzinfo=timezone.utc),
        datetime(2026, 10, 1, 11, 20, tzinfo=timezone.utc),
        datetime(2026, 10, 1, 11, 30, tzinfo=timezone.utc),
    ])

    first = api(_messages_path(scenario.chat_a.id, "?limit=2"), as_auth_id=CUSTOMER_AUTH).json()
    assert first["hasMore"] is True
    assert [message["content"] for message in first["messages"]] == ["extra 1", "extra 2"]

    collected = list(first["messages"])
    page = first
    while page["hasMore"]:
        # SQLite returns naive datetimes; the API requires an explicit offset, as Postgres provides.
        cursor = datetime.fromisoformat(page["messages"][0]["sentAt"]).replace(tzinfo=timezone.utc)
        page = api(
            _messages_path(scenario.chat_a.id, "?limit=2&before=" + cursor.isoformat().replace("+", "%2B")),
            as_auth_id=CUSTOMER_AUTH,
        ).json()
        collected = page["messages"] + collected

    assert [message["content"] for message in collected] == [
        "Hola, ¿a qué hora llegan?",
        "x" * 200,
        "extra 0",
        "extra 1",
        "extra 2",
    ]


@pytest.mark.parametrize("query", ["?limit=0", "?limit=101", "?before=2026-10-01T11:00:00", "?before=not-a-date"])
def test_message_query_inputs_are_validated(api, scenario, query):
    assert api(_messages_path(scenario.chat_a.id, query), as_auth_id=CUSTOMER_AUTH).status_code == 422
