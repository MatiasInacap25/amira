"""Customer claims and consent over completed services.

A claim is allowed on a completed service without consent, inside its claim window, and only once. It holds the
payout by moving the service to disputed. Consent releases the payout early and is refused while a claim is open.
Providers never see the claim actions as available.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from amira_api.clock import utc_now
from amira_api.models import Reclamo, RolUsuario, Servicio, Usuario
from amira_api.payout_service import release_due_payouts
from amira_api.simulated_payout_provider import SimulatedPayoutProvider
from claim_support import add_approved_payment, add_payout_account, complete, db  # noqa: F401  (pytest fixture re-export)
from test_provider_service_actions import Fleet, call, fleet  # noqa: F401  (fixture re-export)
from test_provider_service_routes import CUSTOMER_AUTH, OTHER_CUSTOMER_AUTH, OWNER_AUTH


def _claim_url(service: Servicio) -> str:
    return f"/api/customer/services/{service.id}/claims"


def _consent_url(service: Servicio) -> str:
    return f"/api/customer/services/{service.id}/consent"


def _customer_detail_url(service: Servicio) -> str:
    return f"/api/customer/services/{service.id}"


def _provider_detail_url(service: Servicio) -> str:
    return f"/api/provider/services/{service.id}"


def _claims(db: Session, service: Servicio) -> list[Reclamo]:
    return db.execute(select(Reclamo).where(Reclamo.service_id == service.id)).scalars().all()


def _stored(db: Session, service: Servicio) -> Servicio:
    db.expire_all()
    return db.get(Servicio, service.id)


def _other_customer(db: Session) -> None:
    role = db.execute(select(RolUsuario).where(RolUsuario.code == "client")).scalar_one()
    db.add(Usuario(id=uuid4(), auth_user_id=OTHER_CUSTOMER_AUTH, first_name="Otra", last_name="Clienta",
                   email="otra@example.test", role_id=role.id))
    db.commit()


def test_claim_inside_the_window_disputes_the_service_and_records_the_trimmed_reason(call, db, fleet: Fleet):
    complete(db, fleet.service_a)

    response = call("POST", _claim_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH,
                    json={"reason": "  El sofá llegó roto.  "})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disputed"
    assert body["claimOpen"] is True
    assert body["canClaim"] is False
    assert body["canConsent"] is False
    claims = _claims(db, fleet.service_a)
    assert len(claims) == 1
    assert claims[0].reason == "El sofá llegó roto."
    assert claims[0].status == "open"
    assert _stored(db, fleet.service_a).status == "disputed"


def test_claim_after_the_deadline_is_409_and_writes_nothing(call, db, fleet: Fleet):
    complete(db, fleet.service_a, deadline_in=timedelta(hours=-1))

    response = call("POST", _claim_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH, json={"reason": "Tarde"})

    assert response.status_code == 409
    assert response.json()["detail"] == "The claim window for this service has closed."
    assert _claims(db, fleet.service_a) == []
    assert _stored(db, fleet.service_a).status == "completed"


def test_claim_before_completion_is_409(call, db, fleet: Fleet):
    response = call("POST", _claim_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH, json={"reason": "Antes"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Only completed services can be claimed."
    assert _claims(db, fleet.service_a) == []


def test_second_claim_is_409_while_the_first_is_open(call, db, fleet: Fleet):
    complete(db, fleet.service_a)
    assert call("POST", _claim_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH,
                json={"reason": "Primera"}).status_code == 200

    response = call("POST", _claim_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH, json={"reason": "Segunda"})

    assert response.status_code == 409
    assert response.json()["detail"] == "This service already has an open claim."
    assert [claim.reason for claim in _claims(db, fleet.service_a)] == ["Primera"]


def test_claim_after_consent_is_409(call, db, fleet: Fleet):
    complete(db, fleet.service_a, consent=True)

    response = call("POST", _claim_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH, json={"reason": "Tarde"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Consent was already given for this service."
    assert _claims(db, fleet.service_a) == []


@pytest.mark.parametrize("reason", ["   ", "x" * 1001])
def test_blank_or_oversized_claim_reason_is_422(call, db, fleet: Fleet, reason):
    complete(db, fleet.service_a)

    response = call("POST", _claim_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH, json={"reason": reason})

    assert response.status_code == 422
    assert _claims(db, fleet.service_a) == []


def test_consent_sets_the_timestamp_and_keeps_the_service_completed(call, db, fleet: Fleet):
    complete(db, fleet.service_a)

    response = call("POST", _consent_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["customerConsentAt"] is not None
    assert body["canConsent"] is False
    assert body["canClaim"] is False
    stored = _stored(db, fleet.service_a)
    assert stored.customer_consent_at is not None
    assert stored.status == "completed"


def test_consent_twice_is_409(call, db, fleet: Fleet):
    complete(db, fleet.service_a)
    assert call("POST", _consent_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH).status_code == 200

    response = call("POST", _consent_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 409
    assert response.json()["detail"] == "Consent was already given for this service."


def test_consent_on_a_disputed_service_is_409(call, db, fleet: Fleet):
    complete(db, fleet.service_a)
    assert call("POST", _claim_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH,
                json={"reason": "Dañado"}).status_code == 200

    response = call("POST", _consent_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 409
    assert response.json()["detail"] == "A service with an open claim cannot receive consent."
    assert _stored(db, fleet.service_a).customer_consent_at is None


def test_consent_before_completion_is_409(call, db, fleet: Fleet):
    response = call("POST", _consent_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only completed services can receive consent."
    assert _stored(db, fleet.service_a).customer_consent_at is None


def test_another_customer_gets_404_for_claim_and_consent_and_nothing_is_written(call, db, fleet: Fleet):
    complete(db, fleet.service_a)
    _other_customer(db)

    claim = call("POST", _claim_url(fleet.service_a), as_auth_id=OTHER_CUSTOMER_AUTH, json={"reason": "Ajena"})
    consent = call("POST", _consent_url(fleet.service_a), as_auth_id=OTHER_CUSTOMER_AUTH)

    assert claim.status_code == 404
    assert claim.json()["detail"] == "Service not found."
    assert consent.status_code == 404
    assert consent.json()["detail"] == "Service not found."
    assert _claims(db, fleet.service_a) == []
    assert _stored(db, fleet.service_a).customer_consent_at is None


def test_customer_detail_offers_claim_and_consent_inside_the_window(call, db, fleet: Fleet):
    complete(db, fleet.service_a)

    body = call("GET", _customer_detail_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH).json()

    assert body["canClaim"] is True
    assert body["canConsent"] is True
    assert body["claimOpen"] is False
    assert body["customerConsentAt"] is None


def test_provider_detail_never_offers_claim_or_consent(call, db, fleet: Fleet):
    complete(db, fleet.service_a)

    body = call("GET", _provider_detail_url(fleet.service_a), as_auth_id=OWNER_AUTH).json()

    assert body["canClaim"] is False
    assert body["canConsent"] is False


def _release_payout(db: Session, fleet: Fleet, service: Servicio) -> None:
    """Release a completed service through the payout job, as the cron would once its deadline has passed."""
    add_approved_payment(db, service)
    add_payout_account(db, fleet.company)
    summary = release_due_payouts(db, utc_now(), SimulatedPayoutProvider(app_env="development"))
    assert summary.released == 1


def test_consent_after_the_payout_was_released_is_409_and_changes_nothing(call, db, fleet: Fleet):
    complete(db, fleet.service_a, deadline_in=timedelta(hours=-1))
    _release_payout(db, fleet, fleet.service_a)

    response = call("POST", _consent_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 409
    assert response.json()["detail"] == "The payout for this service has already been released."
    assert _stored(db, fleet.service_a).customer_consent_at is None


def test_released_service_offers_no_consent_to_the_customer(call, db, fleet: Fleet):
    complete(db, fleet.service_a, deadline_in=timedelta(hours=-1))
    _release_payout(db, fleet, fleet.service_a)

    body = call("GET", _customer_detail_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH).json()

    assert body["canConsent"] is False
    assert body["canClaim"] is False


def test_customer_detail_lists_the_assignments_of_the_service(call, db, fleet: Fleet):
    body = call("GET", _customer_detail_url(fleet.service_a), as_auth_id=CUSTOMER_AUTH).json()

    assert body["assignmentCount"] == 1
    assert body["assignments"] == [{
        "driverId": str(fleet.eli.id),
        "driverFirstName": "Eli",
        "vehicleId": str(fleet.van.id),
        "vehicleLabel": f"{fleet.van.brand} {fleet.van.model}",
        "plate": fleet.van.plate,
    }]
    assert body["viewerAssigned"] is False
