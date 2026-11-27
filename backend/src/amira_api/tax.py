"""IVA breakdown of amounts that already include IVA.

Every quoted or paid amount includes IVA 19 %: the net and the IVA are extracted from the total, never added on top.
The net is ``total / 1.19`` rounded half up to whole CLP and the IVA is the remainder, so net + IVA always equals the total.
The platform commission reuses ``commission_for`` from the payout rules, so the rounding lives in one place.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

IVA_RATE_PERCENT = 19


@dataclass(frozen=True)
class AmountBreakdown:
    total: int
    net: int
    iva: int
    commission: int
    commission_net: int
    commission_iva: int
    carrier_amount: int


def split_iva(total: int) -> tuple[int, int]:
    """Return ``(net, iva)`` of a total that includes IVA, in whole CLP."""
    net = int((Decimal(total) * 100 / (100 + IVA_RATE_PERCENT)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return net, total - net


def amount_breakdown(total: int, commission_percent: int) -> AmountBreakdown:
    """Split a paid amount into the carrier's part and Amira's commission, each with its own IVA."""
    # Imported here: payout_service persists its commission invoice through this module, so a top-level import would cycle.
    from amira_api.payout_service import commission_for

    commission = int(commission_for(Decimal(total), commission_percent))
    net, iva = split_iva(total)
    commission_net, commission_iva = split_iva(commission)
    return AmountBreakdown(
        total=total,
        net=net,
        iva=iva,
        commission=commission,
        commission_net=commission_net,
        commission_iva=commission_iva,
        carrier_amount=total - commission,
    )
