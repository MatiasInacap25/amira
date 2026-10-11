"""Shared in-memory database and seed helpers for the claim, consent and payout tests.

The fixture creates the service tables plus the payout tables that the claim and payout code touches. It is a
separate module so the claim and payout test modules share one schema without repeating it.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amira_api.clock import utc_now
from amira_api.models import Base, CuentaDesembolso, Pago, Perfil, Servicio
from chat_support import _register_btrim  # also registers the SQLite JSONB compiler

PAYOUT_TABLES = (
    "Rol_Usuario", "Usuario", "Perfil", "Conductor", "Vehiculo", "Formulario_servicio", "Chat",
    "Cotizacion", "Servicio", "Servicio_Asignacion", "Pago", "Reclamo", "Cuenta_Desembolso", "Desembolso",
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _register_btrim)
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in PAYOUT_TABLES])
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


def complete(
    db: Session, service: Servicio, *, deadline_in: timedelta = timedelta(hours=24), consent: bool = False
) -> None:
    """Move a seeded service to completed with a claim window that closes ``deadline_in`` from now."""
    now = utc_now()
    service.status = "completed"
    service.completed_at = now
    service.payout_deadline_at = now + deadline_in
    if consent:
        service.customer_consent_at = now
    db.commit()


def add_approved_payment(db: Session, service: Servicio, amount: Decimal = Decimal("150000")) -> Pago:
    now = utc_now()
    payment = Pago(
        id=uuid4(),
        quotation_id=service.accepted_quotation_id,
        provider="simulated",
        provider_payment_id=f"sim_{uuid4().hex}",
        idempotency_key=f"quotation:{service.accepted_quotation_id}:attempt:1",
        amount=amount,
        currency="CLP",
        status="approved",
        created_at=now,
        updated_at=now,
    )
    db.add(payment)
    db.commit()
    return payment


def add_payout_account(db: Session, profile: Perfil, *, enabled: bool = True) -> CuentaDesembolso:
    account = CuentaDesembolso(
        id=uuid4(),
        profile_id=profile.id,
        provider="simulated",
        provider_account_id=f"acct_{uuid4().hex}",
        registration_status="active",
        payouts_enabled=enabled,
    )
    db.add(account)
    db.commit()
    return account
