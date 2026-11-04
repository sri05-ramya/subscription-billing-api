"""A fake payment gateway that behaves like Stripe/PayPal for testing.

The result depends on the customer's card_status:
    valid              -> success
    insufficient_funds -> failed (insufficient_funds)
    expired            -> failed (card_expired)
"""

from dataclasses import dataclass
from decimal import Decimal

FAILURE_REASONS = {
    "insufficient_funds": "insufficient_funds",
    "expired": "card_expired",
}


@dataclass
class ChargeResult:
    succeeded: bool
    failure_reason: str | None = None


def charge_card(card_status: str, amount: Decimal, idempotency_key: str) -> ChargeResult:
    """Pretend to charge a card. Real gateways also receive an idempotency key."""
    if card_status == "valid":
        return ChargeResult(succeeded=True)
    return ChargeResult(succeeded=False, failure_reason=FAILURE_REASONS.get(card_status, "declined"))