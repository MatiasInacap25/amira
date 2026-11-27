"""Simulated tax documents: the customer's boleta on approval, Amira's commission invoice on payout, and their read routes.

Everything is simulated: the documents never reach the SII. Folios are sequential per document type, and a replayed
confirmation or payout creates no second document.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.clock import utc_now
from amira_api.models import Desembolso, Pago, Servicio, TaxDocument
from amira_api.payout_service import release_due_payouts
from amira_api.simulated_payout_provider import SimulatedPayoutProvider
from chat_support import (  # noqa: F401  (fixture re-export)
    CUSTOMER_AUTH,
    DRIVER_AUTH,
    OTHER_CUSTOMER_AUTH,
    PROVIDER_AUTH,
    api,
    db,
    scenario,
    seed_account_roles,
)
from claim_support import add_payout_account, complete
from test_payment_routes import (  # noqa: F401  (fixture re-export)
    QUOTATION_BODY,
    _complete,
    _confirm,
    _quote,
    _start,
    _token,
    clock,
    external,
    pay,
    simulator,
    webhook_pay,
)

@pytest.fixture(autouse=True)
def _account_roles(db: Session, scenario) -> None:
    seed_account_roles(db, scenario)


BOLETA_KEYS = {
    "id", "type", "folio", "issuedAt", "issuerName", "issuerTaxId", "recipientName", "recipientTaxId",
    "net", "iva", "total", "currency", "simulated", "serviceId",
}


def _approve_quotation(pay, quotation_id: str, auth=CUSTOMER_AUTH) -> None:
    started = _start(pay, quotation_id, auth=auth).json()
    response = _complete(pay, started["paymentId"], _token(started["checkoutUrl"]), approve=True, auth=auth)
    assert response.status_code == 200, response.text


def _documents(db: Session, tipo: str | None = None) -> list[TaxDocument]:
    statement = select(TaxDocument).order_by(TaxDocument.issued_at, TaxDocument.id)
    if tipo is not None:
        statement = statement.where(TaxDocument.type == tipo)
    return list(db.execute(statement).scalars())


def _release_payout(db: Session, service: Servicio) -> None:
    complete(db, service, consent=True)
    add_payout_account(db, service.provider_profile)
    summary = release_due_payouts(db, utc_now(), SimulatedPayoutProvider(app_env="test"))
    assert summary.released == 1


# Boleta on approval


def test_simulated_approval_issues_one_boleta_in_the_carriers_name(pay, scenario, db: Session):
    scenario.provider_profile.company_tax_id = "76111222-3"
    db.commit()
    quotation_id = _quote(pay, scenario)
    _approve_quotation(pay, quotation_id)

    service = db.execute(select(Servicio)).scalar_one()
    payment = db.execute(select(Pago)).scalar_one()
    [boleta] = _documents(db)

    assert boleta.type == "boleta"
    assert boleta.folio == 1
    assert boleta.service_id == service.id
    assert boleta.payment_id == payment.id
    assert boleta.payout_id is None
    assert (boleta.issuer_name, boleta.issuer_tax_id) == ("Transportes Norte", "76111222-3")
    assert (boleta.recipient_name, boleta.recipient_tax_id) == ("Casey Customer", "12345678-5")
    assert (boleta.net, boleta.iva, boleta.total) == (126050, 23950, 150000)
    assert (boleta.currency, boleta.simulated) == ("CLP", True)
    assert boleta.issued_at is not None


def test_boleta_for_an_independent_driver_carrier_uses_the_owner_full_name_and_national_id(pay, scenario, db: Session):
    scenario.driver_owner.national_id = "11111111-1"
    db.commit()
    quoted = pay(
        f"/api/chats/{scenario.chat_c.id}/quotations",
        as_auth_id=DRIVER_AUTH,
        method="POST",
        json=QUOTATION_BODY,
    )
    assert quoted.status_code == 201, quoted.text
    _approve_quotation(pay, quoted.json()["quotationId"])

    [boleta] = _documents(db, "boleta")

    assert (boleta.issuer_name, boleta.issuer_tax_id) == ("Dana Driver", "11111111-1")
    assert boleta.recipient_name == "Casey Customer"


def test_replayed_webhook_approval_issues_no_second_boleta(webhook_pay, scenario, db: Session, external):
    payment = _pending_payment(webhook_pay, scenario, db)

    first = _confirm(webhook_pay, external, payment, "approved")
    replay = _confirm(webhook_pay, external, payment, "approved")

    assert first.status_code == replay.status_code == 200
    [boleta] = _documents(db, "boleta")
    assert boleta.folio == 1


def test_each_approved_service_gets_the_next_boleta_folio(pay, scenario, db: Session):
    _approve_quotation(pay, _quote(pay, scenario))
    other_quotation = pay(
        f"/api/chats/{scenario.chat_b.id}/quotations",
        as_auth_id=PROVIDER_AUTH,
        method="POST",
        json={**QUOTATION_BODY, "amount": 90000},
    ).json()["quotationId"]
    _approve_quotation(pay, other_quotation, auth=OTHER_CUSTOMER_AUTH)

    boletas = _documents(db, "boleta")

    assert [(document.folio, document.total) for document in boletas] == [(1, 150000), (2, 90000)]


# Commission invoice on payout


def test_releasing_a_payout_issues_the_commission_invoice_to_the_carrier(pay, scenario, db: Session):
    scenario.provider_profile.company_tax_id = "76111222-3"
    db.commit()
    _approve_quotation(pay, _quote(pay, scenario))
    service = db.execute(select(Servicio)).scalar_one()

    _release_payout(db, service)

    desembolso = db.execute(select(Desembolso)).scalar_one()
    [invoice] = _documents(db, "factura_comision")
    assert invoice.folio == 1
    assert invoice.service_id == service.id
    assert invoice.payment_id == desembolso.payment_id
    assert invoice.payout_id == desembolso.id
    assert (invoice.issuer_name, invoice.issuer_tax_id) == ("[DEMO] Amira SpA", "76.000.000-0")
    assert (invoice.recipient_name, invoice.recipient_tax_id) == ("Transportes Norte", "76111222-3")
    assert (invoice.net, invoice.iva, invoice.total) == (12605, 2395, 15000)
    assert invoice.currency == "CLP"


def test_commission_invoice_amounts_for_eighty_thousand_match_the_business_example(pay, scenario, db: Session):
    _approve_quotation(pay, _quote(pay, scenario))
    payment = db.execute(select(Pago)).scalar_one()
    payment.amount = 80000
    db.commit()
    service = db.execute(select(Servicio)).scalar_one()

    _release_payout(db, service)

    [invoice] = _documents(db, "factura_comision")
    assert (invoice.total, invoice.net, invoice.iva) == (8000, 6723, 1277)


def test_running_the_payout_release_twice_issues_one_commission_invoice(pay, scenario, db: Session):
    _approve_quotation(pay, _quote(pay, scenario))
    service = db.execute(select(Servicio)).scalar_one()
    _release_payout(db, service)

    second = release_due_payouts(db, utc_now() + timedelta(days=1), SimulatedPayoutProvider(app_env="test"))

    assert second.released == 0
    assert len(_documents(db, "factura_comision")) == 1


# Read routes


def test_customer_reads_the_boleta_of_their_service_and_never_the_commission_invoice(pay, scenario, db: Session):
    _approve_quotation(pay, _quote(pay, scenario))
    service = db.execute(select(Servicio)).scalar_one()
    _release_payout(db, service)

    response = pay(f"/api/customer/services/{service.id}/documents", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200, response.text
    [item] = response.json()
    assert set(item) == BOLETA_KEYS
    assert (item["type"], item["folio"], item["serviceId"]) == ("boleta", 1, str(service.id))
    assert (item["issuerName"], item["issuerTaxId"]) == ("Transportes Norte", None)
    assert (item["recipientName"], item["recipientTaxId"]) == ("Casey Customer", "12345678-5")
    assert (item["net"], item["iva"], item["total"], item["currency"], item["simulated"]) == (
        126050, 23950, 150000, "CLP", True,
    )


def test_provider_owner_reads_the_boleta_and_the_commission_invoice(pay, scenario, db: Session):
    _approve_quotation(pay, _quote(pay, scenario))
    service = db.execute(select(Servicio)).scalar_one()
    _release_payout(db, service)

    response = pay(f"/api/provider/services/{service.id}/documents", as_auth_id=PROVIDER_AUTH)

    assert response.status_code == 200, response.text
    items = response.json()
    assert [(item["type"], item["folio"]) for item in items] == [("boleta", 1), ("factura_comision", 1)]
    invoice = items[1]
    assert set(invoice) == BOLETA_KEYS
    assert (invoice["issuerName"], invoice["recipientName"]) == ("[DEMO] Amira SpA", "Transportes Norte")
    assert (invoice["net"], invoice["iva"], invoice["total"]) == (12605, 2395, 15000)


def test_unrelated_customer_gets_not_found_for_the_documents(pay, scenario, db: Session):
    _approve_quotation(pay, _quote(pay, scenario))
    service = db.execute(select(Servicio)).scalar_one()

    response = pay(f"/api/customer/services/{service.id}/documents", as_auth_id=OTHER_CUSTOMER_AUTH)

    assert response.status_code == 404


def test_driver_without_the_service_gets_not_found_for_the_provider_documents(pay, scenario, db: Session):
    _approve_quotation(pay, _quote(pay, scenario))
    service = db.execute(select(Servicio)).scalar_one()

    response = pay(f"/api/provider/services/{service.id}/documents", as_auth_id=DRIVER_AUTH)

    assert response.status_code == 404


def test_documents_of_an_unknown_service_are_not_found(pay, scenario):
    response = pay(f"/api/customer/services/{uuid4()}/documents", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 404


def _pending_payment(pay, scenario, db: Session) -> Pago:
    _start(pay, _quote(pay, scenario))
    return db.execute(select(Pago)).scalar_one()
