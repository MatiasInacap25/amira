"""Automatic payout release for completed services, the simulated payout adapter, the CLI and the Render blueprint.

A completed service is released when the customer consented or the claim window closed, and it has no open claim
and no payout yet. Releasing needs an approved payment and an enabled payout account on the provider profile.
Running the release twice creates no second payout, and one failing provider call does not block other services.
The platform keeps a commission of ``payout_commission_percent`` of the gross payment; the provider receives the net.
"""

import logging
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from amira_api import release_payouts
from amira_api.clock import utc_now
from amira_api.models import CuentaDesembolso, Desembolso, Reclamo, Servicio
from amira_api.payout_provider import PayoutProviderError, PayoutRequest, PayoutResult
from amira_api.payout_service import commission_for, release_due_payouts
from amira_api.settings import get_settings
from amira_api.simulated_payout_provider import SimulatedPayoutProvider
from claim_support import add_approved_payment, add_payout_account, complete, db  # noqa: F401  (fixture re-export)
from test_provider_service_actions import Fleet, fleet  # noqa: F401  (fixture re-export)

RENDER_YAML = Path(__file__).parents[2] / "render.yaml"


@pytest.fixture(autouse=True)
def _restore_settings_cache():
    # Autouse fixtures are set up first, so this teardown runs after monkeypatch has undone its environment changes.
    yield
    get_settings.cache_clear()


class RecordingPayoutProvider:
    """Port fake: records each request and fails for the idempotency keys in ``failing_keys``."""

    name = "simulated"

    def __init__(self, failing_keys: frozenset[str] = frozenset()) -> None:
        self.failing_keys = failing_keys
        self.requests: list[PayoutRequest] = []

    def create_payout(self, request: PayoutRequest) -> PayoutResult:
        self.requests.append(request)
        if request.idempotency_key in self.failing_keys:
            raise PayoutProviderError("provider unavailable")
        return PayoutResult(provider_payout_id=f"po_{request.idempotency_key}", status="released")


def _desembolsos(db: Session, service: Servicio) -> list[Desembolso]:
    return db.execute(select(Desembolso).where(Desembolso.service_id == service.id)).scalars().all()


def _funded(db: Session, fleet: Fleet, service: Servicio, amount: Decimal = Decimal("150000")) -> None:
    """Give a seeded service what a release needs: an approved payment and an enabled account on its profile."""
    add_approved_payment(db, service, amount)
    has_account = db.execute(
        select(CuentaDesembolso.id).where(CuentaDesembolso.profile_id == service.profile_id)
    ).first()
    if has_account is None:
        add_payout_account(db, fleet.company)


def test_consented_service_is_released_before_the_deadline(db, fleet: Fleet):
    complete(db, fleet.service_a, consent=True)
    _funded(db, fleet, fleet.service_a)
    provider = RecordingPayoutProvider()

    summary = release_due_payouts(db, utc_now(), provider)

    assert summary.released == 1
    released = _desembolsos(db, fleet.service_a)
    assert len(released) == 1
    assert released[0].net_amount == 135000
    assert released[0].currency == "CLP"
    assert released[0].beneficiary_profile_id == fleet.company.id
    assert released[0].provider_payout_id == f"po_service:{fleet.service_a.id}:payout"
    assert provider.requests[0].amount == 135000
    assert provider.requests[0].destination_account_id.startswith("acct_")


def test_ten_percent_commission_is_withheld_and_the_provider_receives_the_net(db, fleet: Fleet):
    complete(db, fleet.service_a, consent=True)
    _funded(db, fleet, fleet.service_a, Decimal("25000"))
    provider = RecordingPayoutProvider()

    summary = release_due_payouts(db, utc_now(), provider, commission_percent=10)

    assert summary.released == 1
    assert _desembolsos(db, fleet.service_a)[0].net_amount == 22500
    assert provider.requests[0].amount == 22500


def test_commission_rounds_half_up_to_whole_pesos(db, fleet: Fleet):
    # 10% of 12345 is 1234.5, which rounds up to 1235 (not banker's rounding, not a float artifact).
    complete(db, fleet.service_a, consent=True)
    _funded(db, fleet, fleet.service_a, Decimal("12345"))
    provider = RecordingPayoutProvider()

    release_due_payouts(db, utc_now(), provider, commission_percent=10)

    net_amount = _desembolsos(db, fleet.service_a)[0].net_amount
    assert net_amount == 11110
    assert provider.requests[0].amount == net_amount


@pytest.mark.parametrize("percent", [-1, 100, 150])
def test_out_of_range_commission_override_is_rejected_before_any_service_is_processed(db, fleet: Fleet, percent: int):
    complete(db, fleet.service_a, consent=True)
    _funded(db, fleet, fleet.service_a)
    provider = RecordingPayoutProvider()

    with pytest.raises(ValueError, match="between 0 and 99"):
        release_due_payouts(db, utc_now(), provider, commission_percent=percent)

    assert provider.requests == []
    assert _desembolsos(db, fleet.service_a) == []


@pytest.mark.parametrize("percent", [-1, 100])
def test_commission_for_rejects_a_percent_outside_zero_to_ninety_nine(percent: int):
    with pytest.raises(ValueError, match="between 0 and 99"):
        commission_for(Decimal("12345"), percent)


def test_zero_percent_commission_releases_the_gross_amount(db, fleet: Fleet):
    complete(db, fleet.service_a, consent=True)
    _funded(db, fleet, fleet.service_a)
    provider = RecordingPayoutProvider()

    release_due_payouts(db, utc_now(), provider, commission_percent=0)

    assert _desembolsos(db, fleet.service_a)[0].net_amount == 150000
    assert provider.requests[0].amount == 150000


def test_commission_defaults_to_the_payout_commission_setting(db, fleet: Fleet, monkeypatch):
    monkeypatch.setenv("PAYOUT_COMMISSION_PERCENT", "20")
    get_settings.cache_clear()
    complete(db, fleet.service_a, consent=True)
    _funded(db, fleet, fleet.service_a, Decimal("25000"))

    release_due_payouts(db, utc_now(), RecordingPayoutProvider())

    assert _desembolsos(db, fleet.service_a)[0].net_amount == 20000


def test_service_past_its_deadline_is_released_without_consent(db, fleet: Fleet):
    complete(db, fleet.service_a, deadline_in=timedelta(hours=-1))
    _funded(db, fleet, fleet.service_a)

    summary = release_due_payouts(db, utc_now(), RecordingPayoutProvider())

    assert summary.released == 1
    assert len(_desembolsos(db, fleet.service_a)) == 1


def test_service_before_its_deadline_without_consent_is_skipped(db, fleet: Fleet):
    complete(db, fleet.service_a, deadline_in=timedelta(hours=1))
    _funded(db, fleet, fleet.service_a)
    provider = RecordingPayoutProvider()

    summary = release_due_payouts(db, utc_now(), provider)

    assert summary.released == 0
    assert _desembolsos(db, fleet.service_a) == []
    assert provider.requests == []


def test_disputed_service_is_never_released(db, fleet: Fleet):
    complete(db, fleet.service_a, deadline_in=timedelta(hours=-1))
    _funded(db, fleet, fleet.service_a)
    fleet.service_a.status = "disputed"
    db.add(Reclamo(id=uuid4(), service_id=fleet.service_a.id, user_id=fleet.service_a.customer_id,
                   reason="Dañado", status="open", created_at=utc_now()))
    db.commit()

    summary = release_due_payouts(db, utc_now(), RecordingPayoutProvider())

    assert summary.released == 0
    assert _desembolsos(db, fleet.service_a) == []


def test_completed_service_with_an_open_claim_is_never_released(db, fleet: Fleet):
    complete(db, fleet.service_a, deadline_in=timedelta(hours=-1))
    _funded(db, fleet, fleet.service_a)
    db.add(Reclamo(id=uuid4(), service_id=fleet.service_a.id, user_id=fleet.service_a.customer_id,
                   reason="Dañado", status="open", created_at=utc_now()))
    db.commit()

    summary = release_due_payouts(db, utc_now(), RecordingPayoutProvider())

    assert summary.released == 0
    assert _desembolsos(db, fleet.service_a) == []


def test_missing_payout_account_is_skipped_and_counted(db, fleet: Fleet):
    complete(db, fleet.service_a, consent=True)
    add_approved_payment(db, fleet.service_a)
    provider = RecordingPayoutProvider()

    summary = release_due_payouts(db, utc_now(), provider)

    assert summary.released == 0
    assert summary.missing_account == 1
    assert _desembolsos(db, fleet.service_a) == []
    assert provider.requests == []


def test_disabled_payout_account_counts_as_missing(db, fleet: Fleet):
    complete(db, fleet.service_a, consent=True)
    add_approved_payment(db, fleet.service_a)
    add_payout_account(db, fleet.company, enabled=False)

    summary = release_due_payouts(db, utc_now(), RecordingPayoutProvider())

    assert summary.missing_account == 1
    assert _desembolsos(db, fleet.service_a) == []


def test_completed_service_without_an_approved_payment_is_counted_as_missing_payment(db, fleet: Fleet):
    complete(db, fleet.service_a, consent=True)
    add_payout_account(db, fleet.company)

    summary = release_due_payouts(db, utc_now(), RecordingPayoutProvider())

    assert summary.released == 0
    assert summary.missing_payment == 1
    assert _desembolsos(db, fleet.service_a) == []


def test_running_the_release_twice_creates_no_duplicate_payout(db, fleet: Fleet):
    complete(db, fleet.service_a, consent=True)
    _funded(db, fleet, fleet.service_a)
    provider = RecordingPayoutProvider()

    first = release_due_payouts(db, utc_now(), provider)
    second = release_due_payouts(db, utc_now(), provider)

    assert first.released == 1
    assert second.released == 0
    assert len(_desembolsos(db, fleet.service_a)) == 1
    assert db.execute(select(func.count()).select_from(Desembolso)).scalar_one() == 1


def test_one_failing_provider_call_does_not_block_the_other_services(db, fleet: Fleet):
    complete(db, fleet.service_a, consent=True)
    complete(db, fleet.service_same_day, consent=True)
    _funded(db, fleet, fleet.service_a)
    _funded(db, fleet, fleet.service_same_day)
    failing_key = f"service:{fleet.service_a.id}:payout"
    provider = RecordingPayoutProvider(failing_keys=frozenset({failing_key}))

    summary = release_due_payouts(db, utc_now(), provider)

    assert summary.failed == 1
    assert summary.released == 1
    assert _desembolsos(db, fleet.service_a) == []
    assert len(_desembolsos(db, fleet.service_same_day)) == 1


def test_simulated_payout_adapter_refuses_to_run_in_production():
    with pytest.raises(RuntimeError, match="APP_ENV"):
        SimulatedPayoutProvider(app_env="production")


def test_simulated_payout_adapter_is_deterministic_per_idempotency_key():
    provider = SimulatedPayoutProvider(app_env="development")
    request = PayoutRequest(idempotency_key="service:abc:payout", amount=150000, currency="CLP",
                            destination_account_id="acct_1")

    assert provider.create_payout(request).provider_payout_id == provider.create_payout(request).provider_payout_id


def test_release_command_refuses_production_and_exits_non_zero(monkeypatch, caplog):
    # get_settings is cached: clear it so the APP_ENV set here is the one the command reads.
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "production")
    try:
        with caplog.at_level(logging.ERROR, logger="amira_api.release_payouts"):
            assert release_payouts.main() == 1
    finally:
        get_settings.cache_clear()

    assert "Payout release cannot run: The simulated payout provider requires APP_ENV to be one of:" in caplog.text


def test_render_blueprint_has_no_payout_cron_until_a_real_adapter_exists():
    # PyYAML is only a transitive dependency, so this reads the service list and command lines as plain text.
    lines = RENDER_YAML.read_text(encoding="utf-8").splitlines()
    service_types = [line.split("type:", 1)[1].strip() for line in lines if line.lstrip().startswith("- type:")]
    command_lines = [line for line in lines if "command:" in line.lower()]

    assert service_types, "render.yaml must declare at least one service"
    assert "cron" not in service_types, "render.yaml must not deploy the payout cron without a real payout adapter"
    assert not any("release_payouts" in line for line in command_lines)
