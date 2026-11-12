"""Proration: fair price when a customer changes plan in the middle of a billing period."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def prorate(
    old_price: Decimal,
    new_price: Decimal,
    period_start: datetime,
    period_end: datetime,
    change_at: datetime,
) -> dict:
    """Example: Basic $10 -> Pro $25 exactly halfway through the month:
    credit $5.00, new charge $12.50, amount due $7.50.
    """
    total_seconds = (period_end - period_start).total_seconds()
    remaining_seconds = max((period_end - change_at).total_seconds(), 0)
    fraction = Decimal(str(remaining_seconds / total_seconds)) if total_seconds > 0 else Decimal(0)

    unused_credit = (old_price * fraction).quantize(CENT, rounding=ROUND_HALF_UP)
    new_plan_charge = (new_price * fraction).quantize(CENT, rounding=ROUND_HALF_UP)

    return {
        "fraction_remaining": round(float(fraction), 4),
        "unused_credit": unused_credit,
        "new_plan_charge": new_plan_charge,
        "amount_due": new_plan_charge - unused_credit,
    }