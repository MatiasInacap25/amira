"""Simulated tax documents, written inside the business transaction that creates them.

A boleta is issued to the customer in the carrier's name when a payment is approved. Amira's commission invoice is issued
to the carrier when the payout is released. Both run in the caller's transaction, take the next folio of their type, and
are idempotent per service and type: a replay inserts nothing (ON CONFLICT DO NOTHING). Nothing is sent to the SII.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from amira_api.models import Desembolso, Pago, Perfil, Servicio, TaxDocument, Usuario
from amira_api.settings import get_settings
from amira_api.tax import split_iva
from amira_api.tax_document_schemas import TaxDocumentView

BOLETA = "boleta"
COMMISSION_INVOICE = "factura_comision"
CURRENCY = "CLP"


@dataclass(frozen=True)
class TaxParty:
    name: str
    tax_id: str | None


def _full_name(user: Usuario) -> str:
    return f"{user.first_name} {user.last_name}"


def carrier_party(profile: Perfil) -> TaxParty:
    """A company carrier is named by its profile; an independent driver is named by the owner's own identity."""
    if profile.kind == "independent_driver":
        return TaxParty(_full_name(profile.owner), profile.owner.national_id)
    return TaxParty(profile.name, profile.company_tax_id)


def customer_party(customer: Usuario) -> TaxParty:
    return TaxParty(_full_name(customer), customer.national_id)


def amira_party() -> TaxParty:
    settings = get_settings()
    return TaxParty(settings.amira_legal_name, settings.amira_tax_id)


def _lock_folio_sequence(session: Session, tipo: str) -> None:
    # PostgreSQL serializes folio allocation per type until the caller commits, so max + 1 cannot repeat.
    # The unique (Tipo, Folio) constraint stays the guard; other dialects run single-connection tests.
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"tax_document_folio:{tipo}"})


def _next_folio(session: Session, tipo: str) -> int:
    _lock_folio_sequence(session, tipo)
    current = session.execute(select(func.max(TaxDocument.folio)).where(TaxDocument.type == tipo)).scalar_one()
    return (current or 0) + 1


def _insert_once(session: Session, values: dict) -> None:
    # The same ON CONFLICT DO NOTHING shape as the terms acceptance insert, dialect chosen for the bound engine.
    insert = sqlite.insert if session.get_bind().dialect.name == "sqlite" else postgresql.insert
    table = TaxDocument.__table__
    session.execute(
        insert(TaxDocument)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[table.c["ID_Servicio"], table.c["Tipo"]])
    )


def _issue(
    session: Session,
    *,
    tipo: str,
    service_id: UUID,
    payment_id: UUID,
    payout_id: UUID | None,
    issuer: TaxParty,
    recipient: TaxParty,
    total: int,
    now: datetime,
) -> None:
    net, iva = split_iva(total)
    folio = _next_folio(session, tipo)
    _insert_once(
        session,
        {
            "id": uuid4(),
            "service_id": service_id,
            "payment_id": payment_id,
            "payout_id": payout_id,
            "type": tipo,
            "folio": folio,
            "issuer_name": issuer.name,
            "issuer_tax_id": issuer.tax_id,
            "recipient_name": recipient.name,
            "recipient_tax_id": recipient.tax_id,
            "net": Decimal(net),
            "iva": Decimal(iva),
            "total": Decimal(total),
            "currency": CURRENCY,
            "issued_at": now,
            "simulated": True,
        },
    )


def issue_boleta(
    session: Session, *, service: Servicio, payment: Pago, customer: Usuario, carrier: Perfil, now: datetime
) -> None:
    """The customer's boleta for an approved payment, issued in the carrier's name by mandate."""
    _issue(
        session,
        tipo=BOLETA,
        service_id=service.id,
        payment_id=payment.id,
        payout_id=None,
        issuer=carrier_party(carrier),
        recipient=customer_party(customer),
        total=int(payment.amount),
        now=now,
    )


def issue_commission_invoice(
    session: Session,
    *,
    service: Servicio,
    payment: Pago,
    payout: Desembolso,
    carrier: Perfil,
    commission: int,
    now: datetime,
) -> None:
    """Amira's invoice to the carrier for the commission withheld from a released payout."""
    _issue(
        session,
        tipo=COMMISSION_INVOICE,
        service_id=service.id,
        payment_id=payment.id,
        payout_id=payout.id,
        issuer=amira_party(),
        recipient=carrier_party(carrier),
        total=commission,
        now=now,
    )


def document_views(session: Session, service_id: UUID, types: tuple[str, ...]) -> list[TaxDocumentView]:
    rows = session.execute(
        select(TaxDocument)
        .where(TaxDocument.service_id == service_id, TaxDocument.type.in_(types))
        .order_by(TaxDocument.issued_at, TaxDocument.id)
    ).scalars()
    return [
        TaxDocumentView(
            id=row.id,
            type=row.type,
            folio=row.folio,
            issued_at=row.issued_at,
            issuer_name=row.issuer_name,
            issuer_tax_id=row.issuer_tax_id,
            recipient_name=row.recipient_name,
            recipient_tax_id=row.recipient_tax_id,
            net=int(row.net),
            iva=int(row.iva),
            total=int(row.total),
            currency=row.currency,
            simulated=row.simulated,
            service_id=row.service_id,
        )
        for row in rows
    ]
