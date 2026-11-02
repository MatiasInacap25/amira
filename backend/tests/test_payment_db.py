"""Simulated payments through the real routes, asserted against PostgreSQL in a fresh session.

The in-memory SQLite tests in test_payment_routes.py cannot prove the transaction is persisted, nor that the
PostgreSQL-only constraints accept the rows. This module drops and recreates the tables it needs, so it is skipped
unless AMIRA_TEST_DATABASE_URL names a disposable local database (see postgres_support).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Table
from sqlalchemy.orm import Session

from amira_api.auth import get_current_user
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import (
    Base,
    Chat,
    ChatParticipante,
    Commune,
    Cotizacion,
    FormularioServicio,
    Pago,
    Perfil,
    Region,
    RolPerfil,
    RolUsuario,
    Servicio,
    TipoServicio,
    Usuario,
)
from amira_api.payment_routes import get_payment_provider, get_simulated_provider
from amira_api.settings import get_settings
from amira_api.simulated_payment_provider import SimulatedPaymentProvider
from chat_support import CUSTOMER_AUTH, PROVIDER_AUTH, _chat, _profile, _user, api
from postgres_support import disposable_test_database_url, disposable_test_engine
from test_payment_routes import FRONTEND, QUOTATION_BODY, SECRET, _complete, _quote, _settings, _start, _token

# Tables the payment path reads or writes, plus every table their foreign keys point at (Servicio alone references
# trip and stop tables, so the closure is computed from the ORM metadata rather than listed by hand).
PAYMENT_TABLES = (
    "Regiones",
    "Comunas",
    "Rol_Usuario",
    "Usuario",
    "Rol_Perfil",
    "Perfil",
    "Tipos_Servicio",
    "Formulario_servicio",
    "Chat",
    "Chat_participantes",
    "Cotizacion",
    "Pago",
    "Servicio",
)


def _tables_with_dependencies(names: tuple[str, ...]) -> list[Table]:
    pending = [Base.metadata.tables[name] for name in names]
    found: dict[str, Table] = {}
    while pending:
        table = pending.pop()
        if table.name in found:
            continue
        found[table.name] = table
        pending.extend(foreign_key.column.table for foreign_key in table.foreign_keys)
    return list(found.values())


@dataclass
class PaymentScenario:
    """The seeded rows the payment routes need. Shape matches what test_payment_routes._quote reads (chat_a)."""

    customer: Usuario
    provider_profile: Perfil
    service_type: TipoServicio
    chat_a: Chat


@pytest.fixture
def db():
    database_url = disposable_test_database_url()
    engine = disposable_test_engine(database_url)
    tables = _tables_with_dependencies(PAYMENT_TABLES)
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    try:
        with Session(engine) as session:
            yield session
    finally:
        Base.metadata.drop_all(engine, tables=tables)
        engine.dispose()


@pytest.fixture
def pay(api, db):
    """Same wiring as test_payment_routes.pay: only auth and settings are overridden, and APP_ENV=test enables the simulator."""
    simulator = SimulatedPaymentProvider(secret=SECRET, frontend_base_url=FRONTEND, app_env="test")
    app.dependency_overrides[get_payment_provider] = lambda: simulator
    app.dependency_overrides[get_simulated_provider] = lambda: simulator
    app.dependency_overrides[get_settings] = lambda: _settings()
    yield api
    for dependency in (get_payment_provider, get_simulated_provider, get_settings, get_db_session, get_current_user):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture
def scenario(db: Session) -> PaymentScenario:
    client_role = RolUsuario(id=uuid4(), name="client", code="client")
    company_owner_role = RolUsuario(id=uuid4(), name="company_owner", code="company_owner")
    company_role = RolPerfil(id=uuid4(), name="company", code="company")
    santiago = Commune(code="13101", region_code="13", name="Santiago")
    valparaiso = Commune(code="05101", region_code="05", name="Valparaíso")
    mudanzas = TipoServicio(id=uuid4(), name="Mudanzas", slug="mudanzas")
    db.add_all([
        Region(code="13", name="Metropolitana de Santiago", order=1),
        Region(code="05", name="Valparaíso", order=2),
        client_role,
        company_owner_role,
        company_role,
        santiago,
        valparaiso,
        mudanzas,
    ])
    db.flush()

    # _user and _profile create a random role id; the real role rows exist here, so point the rows at them.
    customer = _user(db, auth_id=CUSTOMER_AUTH, first="Casey", last="Customer", email="casey.customer@example.test")
    customer.role_id = client_role.id
    provider_owner = _user(db, auth_id=PROVIDER_AUTH, first="Pat", last="Provider", email="pat@example.test")
    provider_owner.role_id = company_owner_role.id
    profile = _profile(db, owner=provider_owner, name="Transportes Norte", kind="company")
    profile.role_id = company_role.id
    db.flush()
    chat = _chat(db, customer=customer, profile=profile, service=mudanzas, origin=santiago, destination=valparaiso,
                 created_at=datetime(2026, 10, 1, 10, tzinfo=timezone.utc), provider_owner=provider_owner)
    db.commit()
    return PaymentScenario(customer=customer, provider_profile=profile, service_type=mudanzas, chat_a=chat)


def _insert_other_pending_quotation(db: Session, scenario: PaymentScenario) -> UUID:
    # The quotation route supersedes earlier pending ones, so a second pending quotation is inserted directly to
    # prove that approval supersedes it.
    now = utc_now()
    other = Cotizacion(
        id=uuid4(),
        chat_id=scenario.chat_a.id,
        status="pending",
        amount=Decimal("99000"),
        origin="Santiago",
        destination="Valparaíso",
        service_at=now + timedelta(days=5),
        description="Cotización alternativa",
        created_at=now,
        service_type_id=scenario.service_type.id,
        expires_at=now + timedelta(hours=48),
        is_exclusive=False,
        currency="CLP",
    )
    db.add(other)
    db.commit()
    return other.id


def test_approved_simulated_payment_is_persisted_in_postgres(pay, scenario, db: Session):
    quotation_id = _quote(pay, scenario)
    other_id = _insert_other_pending_quotation(db, scenario)
    started = _start(pay, quotation_id).json()
    token = _token(started["checkoutUrl"])

    response = _complete(pay, started["paymentId"], token, approve=True)

    assert response.status_code == 200
    # A new session reads only what was committed to PostgreSQL.
    with Session(db.get_bind()) as fresh:
        payment = fresh.query(Pago).one()
        assert payment.status == "approved"
        assert payment.checkout_used_at is not None

        quotation = fresh.get(Cotizacion, UUID(quotation_id))
        assert quotation.status == "paid"
        assert quotation.accepted_at is not None
        assert fresh.get(Cotizacion, other_id).status == "superseded"

        service = fresh.query(Servicio).one()
        assert service.status == "confirmed"
        assert service.amount == Decimal("150000")
        assert service.profile_id == scenario.provider_profile.id
        assert service.customer_id == scenario.customer.id
        assert service.form_id == scenario.chat_a.form_id
        assert service.accepted_quotation_id == quotation.id
        assert str(service.id) == response.json()["serviceId"]

    # The checkout link is single-use: a retry with the same approval returns the stored result and creates nothing.
    retry = _complete(pay, started["paymentId"], token, approve=True)
    assert retry.status_code == 200
    assert retry.json() == response.json()
    with Session(db.get_bind()) as fresh:
        assert fresh.query(Servicio).count() == 1


def test_rejected_simulated_payment_is_persisted_and_creates_no_service(pay, scenario, db: Session):
    quotation_id = _quote(pay, scenario)
    started = _start(pay, quotation_id).json()

    response = _complete(pay, started["paymentId"], _token(started["checkoutUrl"]), approve=False)

    assert response.status_code == 200
    with Session(db.get_bind()) as fresh:
        assert fresh.query(Pago).one().status == "rejected"
        assert fresh.get(Cotizacion, UUID(quotation_id)).status == "pending"
        assert fresh.query(Servicio).count() == 0
