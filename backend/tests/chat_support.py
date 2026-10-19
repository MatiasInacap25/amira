"""Shared chat fixtures: an in-memory database seeded with customers, providers, drivers and chats.

Imported by the chat, quotation and payment test modules. Postgres-only CHECK constraints (regex `~`) are not
emitted for the two lookup tables, which are created with plain DDL. Everything else comes from the ORM metadata.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
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


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(_type, _compiler, **_kw) -> str:
    # SQLite has no JSONB; the tests never read agreed_terms, so JSON is enough for DDL.
    return "JSON"


CUSTOMER_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e01")
PROVIDER_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e02")
DRIVER_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e03")
OTHER_CUSTOMER_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e04")
UNKNOWN_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e05")

SECRET_CONTACT_VALUES = ("+56911112222", "+56922223333", "casey.customer@example.test", "12345678-5", "pat@example.test")


def _register_btrim(connection, _record) -> None:
    # The unique email index is an expression over btrim(), which SQLite does not provide.
    connection.create_function("btrim", 1, lambda value: value.strip() if value else value, deterministic=True)


def _register_pg_notify(notifications: list[tuple[str, str]]):
    # SQLite has no LISTEN/NOTIFY. The fake records (channel, payload) so tests can see what a commit would announce.
    def record(channel: str, payload: str) -> None:
        notifications.append((channel, payload))

    def register(connection, _record) -> None:
        connection.create_function("pg_notify", 2, record)

    return register


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    notifications: list[tuple[str, str]] = []
    event.listen(engine, "connect", _register_btrim)
    event.listen(engine, "connect", _register_pg_notify(notifications))
    tables = (
        "Usuario",
        "Perfil",
        "Formulario_servicio",
        "Chat",
        "Chat_participantes",
        "Mensajes",
        "Cotizacion",
        "Pago",
        "Servicio",
    )
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in tables])
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE "Comunas" ("Codigo" VARCHAR(5) PRIMARY KEY, "Codigo_Region" VARCHAR(2) NOT NULL, "Nombre" VARCHAR(120) NOT NULL)'
        ))
        connection.execute(text(
            'CREATE TABLE "Tipos_Servicio" ("ID" CHAR(32) PRIMARY KEY, "Nombre_servicio" VARCHAR(120) NOT NULL, "Slug" VARCHAR(120) NOT NULL)'
        ))
    with Session(engine) as session:
        session.info["notifications"] = notifications
        yield session
    engine.dispose()


@pytest.fixture
def api(db):
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app)

    def get(path: str, *, as_auth_id: UUID, method: str = "GET", json: dict | None = None, headers: dict | None = None):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=as_auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
        return client.request(method, path, json=json, headers=headers)

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
