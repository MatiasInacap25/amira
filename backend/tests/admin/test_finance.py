from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from claim_support import add_approved_payment, complete, db  # noqa: F401
from test_provider_service_actions import fleet  # noqa: F401
from test_auth import USER_ID

from amira_api.clock import utc_now
from amira_api.models import Reembolso
from amira_api.settings import Settings


def test_summary_applies_mandate_and_checks_payout_eligibility(db, fleet):
    from amira_api.admin.finance import finance_summary, reporting_period

    now = utc_now()
    Reembolso.__table__.create(db.get_bind())
    complete(db, fleet.service_a, deadline_in=timedelta(hours=-1))
    add_approved_payment(db, fleet.service_a, Decimal("80000"))
    result = finance_summary(db, reporting_period(None, None, now), now, Settings())
    assert result["collected"] == 80000
    assert result["commission_gross"] == 8000
    assert result["commission_net"] == 6723
    assert result["commission_iva"] == result["platform_iva"] == 1277
    assert result["payout_due"] == 72000
    assert result["payout_due_count"] == 1


def test_settings_reports_configured_members_without_credentials(db):
    from amira_api.admin.finance import configuration

    settings = Settings(app_env="test", admin_user_ids={UUID(USER_ID)}, payment_provider="simulated",
                        payment_simulator_secret="not-for-admin-output", frontend_base_url="http://local.test")
    result = configuration(db, settings)
    assert result["payment_adapter"] == "simulated"
    assert result["payout_adapter"] == "simulated"
    assert result["commission_percent"] == 10
    assert result["admins"] == [{"user_id": UUID(USER_ID), "email": None}]
    assert "not-for-admin-output" not in repr(result)
    assert result["claim_window_hours"] == 24


def test_movements_and_commission_breakdown(db, fleet):
    from amira_api.admin.finance import movements, provider_commissions, reporting_period, timeseries

    Reembolso.__table__.create(db.get_bind())
    payment = add_approved_payment(db, fleet.service_a, Decimal("80000"))
    now = utc_now()
    period = reporting_period(None, None, now)
    activity = movements(db, 10)
    assert activity[0]["id"] == payment.id
    assert activity[0]["service_id"] == fleet.service_a.id
    assert sum(day["commission"] for day in timeseries(db, period, 10)) == 8000
    assert provider_commissions(db, period, 10)[0]["commission_iva"] == 1277
