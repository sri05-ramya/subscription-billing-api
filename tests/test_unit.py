"""Unit tests for pure functions: no database, no web server."""

from datetime import datetime
from decimal import Decimal

from app.dates import add_one_month
from app.payment_gateway import charge_card
from app.proration import prorate
from app.security import create_access_token, decode_access_token, hash_password, verify_password


# ---------- add_one_month ----------


def test_add_one_month_normal_day():
    assert add_one_month(datetime(2026, 11, 4)) == datetime(2026, 12, 4)


def test_add_one_month_end_of_january_goes_to_end_of_february():
    assert add_one_month(datetime(2027, 1, 31)) == datetime(2027, 2, 28)


def test_add_one_month_leap_year():
    assert add_one_month(datetime(2028, 1, 31)) == datetime(2028, 2, 29)


def test_add_one_month_december_goes_to_next_year():
    assert add_one_month(datetime(2026, 12, 15)) == datetime(2027, 1, 15)


# ---------- proration ----------


def test_upgrade_halfway_pays_the_difference():
    result = prorate(Decimal("10"), Decimal("25"), datetime(2026, 12, 1), datetime(2026, 12, 31), datetime(2026, 12, 16))
    assert result["unused_credit"] == Decimal("5.00")
    assert result["new_plan_charge"] == Decimal("12.50")
    assert result["amount_due"] == Decimal("7.50")


def test_downgrade_gives_negative_amount():
    result = prorate(Decimal("25"), Decimal("10"), datetime(2026, 12, 1), datetime(2026, 12, 31), datetime(2026, 12, 16))
    assert result["amount_due"] == Decimal("-7.50")


def test_change_at_period_end_costs_nothing():
    result = prorate(Decimal("10"), Decimal("25"), datetime(2026, 12, 1), datetime(2026, 12, 31), datetime(2026, 12, 31))
    assert result["amount_due"] == Decimal("0.00")


# ---------- fake payment gateway ----------


def test_valid_card_succeeds():
    assert charge_card("valid", Decimal("10"), "k1").succeeded is True


def test_insufficient_funds_fails_with_reason():
    result = charge_card("insufficient_funds", Decimal("10"), "k2")
    assert result.succeeded is False
    assert result.failure_reason == "insufficient_funds"


def test_expired_card_fails_with_reason():
    assert charge_card("expired", Decimal("10"), "k3").failure_reason == "card_expired"


# ---------- security ----------


def test_password_hash_is_not_the_password_and_verifies():
    hashed = hash_password("Secret123")
    assert "Secret123" not in hashed
    assert verify_password("Secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_same_password_gets_different_hashes():
    assert hash_password("Secret123") != hash_password("Secret123")


def test_token_round_trip():
    token = create_access_token(7, "admin")
    claims = decode_access_token(token)
    assert claims["sub"] == "7"
    assert claims["role"] == "admin"