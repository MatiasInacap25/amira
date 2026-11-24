"""IVA breakdown rules: an amount includes IVA 19 %, so the net and the IVA are extracted from the total (S0, S1)."""

import pytest

from amira_api.settings import Settings
from amira_api.tax import IVA_RATE_PERCENT, AmountBreakdown, amount_breakdown, split_iva


def test_iva_rate_is_nineteen_percent():
    assert IVA_RATE_PERCENT == 19


@pytest.mark.parametrize(
    ("total", "net", "iva"),
    [
        (0, 0, 0),
        (1, 1, 0),
        (119, 100, 19),
        # 80.000 / 1,19 = 67.226,89: half-up gives 67.227, so the IVA is 12.773 (truncation would give 12.774).
        (80000, 67227, 12773),
        (10001, 8404, 1597),
        (150000, 126050, 23950),
    ],
)
def test_split_iva_extracts_the_iva_from_a_total_that_includes_it(total: int, net: int, iva: int):
    assert split_iva(total) == (net, iva)
    assert net + iva == total


def test_split_iva_never_adds_iva_on_top_of_the_total():
    net, iva = split_iva(80000)

    assert net + iva == 80000
    assert net != 80000


def test_amount_breakdown_for_eighty_thousand_at_ten_percent_matches_the_business_example():
    assert amount_breakdown(80000, 10) == AmountBreakdown(
        total=80000,
        net=67227,
        iva=12773,
        commission=8000,
        commission_net=6723,
        commission_iva=1277,
        carrier_amount=72000,
    )


def test_amount_breakdown_rounds_the_commission_half_up_before_extracting_its_iva():
    # 10 % of 12.345 is 1.234,5, which rounds up to 1.235 (the same rule as the payout commission).
    breakdown = amount_breakdown(12345, 10)

    assert breakdown.commission == 1235
    assert breakdown.commission_net + breakdown.commission_iva == 1235
    assert breakdown.carrier_amount == 11110


def test_amount_breakdown_of_zero_is_all_zero():
    assert amount_breakdown(0, 10) == AmountBreakdown(
        total=0, net=0, iva=0, commission=0, commission_net=0, commission_iva=0, carrier_amount=0
    )


def test_amount_breakdown_refuses_a_commission_percent_outside_zero_to_ninety_nine():
    with pytest.raises(ValueError):
        amount_breakdown(80000, 100)


def test_amira_legal_identity_defaults_are_demo_values():
    settings = Settings(_env_file=None)

    assert settings.amira_legal_name == "[DEMO] Amira SpA"
    assert settings.amira_tax_id == "76.000.000-0"
