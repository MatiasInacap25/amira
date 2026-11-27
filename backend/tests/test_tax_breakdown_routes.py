"""IVA breakdown in API responses: quotations carry net and IVA; service details carry the breakdown by viewer role."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.models import Servicio
from chat_support import CUSTOMER_AUTH, PROVIDER_AUTH, api, db, scenario, seed_account_roles  # noqa: F401  (fixture re-export)
from test_payment_routes import (  # noqa: F401  (fixture re-export)
    QUOTATION_BODY,
    _complete,
    _quote,
    _start,
    _token,
    clock,
    pay,
    simulator,
)


@pytest.fixture(autouse=True)
def _account_roles(db: Session, scenario) -> None:
    seed_account_roles(db, scenario)


def test_quotation_response_splits_the_amount_into_net_and_iva(pay, scenario):
    response = pay(
        f"/api/chats/{scenario.chat_a.id}/quotations",
        as_auth_id=PROVIDER_AUTH,
        method="POST",
        json={**QUOTATION_BODY, "amount": 80000},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["amount"], body["netAmount"], body["ivaAmount"]) == (80000, 67227, 12773)


def _approved_service(pay, scenario, db: Session) -> Servicio:
    started = _start(pay, _quote(pay, scenario)).json()
    response = _complete(pay, started["paymentId"], _token(started["checkoutUrl"]), approve=True)
    assert response.status_code == 200, response.text
    return db.execute(select(Servicio)).scalar_one()


def test_customer_service_detail_shows_total_net_and_iva_without_commission(pay, scenario, db: Session):
    service = _approved_service(pay, scenario, db)

    response = pay(f"/api/customer/services/{service.id}", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200, response.text
    assert response.json()["amountBreakdown"] == {
        "total": 150000,
        "net": 126050,
        "iva": 23950,
        "commission": None,
        "commissionNet": None,
        "commissionIva": None,
        "carrierAmount": None,
    }


def test_provider_service_detail_shows_the_commission_and_what_the_carrier_receives(pay, scenario, db: Session):
    service = _approved_service(pay, scenario, db)

    response = pay(f"/api/provider/services/{service.id}", as_auth_id=PROVIDER_AUTH)

    assert response.status_code == 200, response.text
    assert response.json()["amountBreakdown"] == {
        "total": 150000,
        "net": 126050,
        "iva": 23950,
        "commission": 15000,
        "commissionNet": 12605,
        "commissionIva": 2395,
        "carrierAmount": 135000,
    }
