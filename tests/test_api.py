"""API tests: call the real endpoints like Swagger would, against the billing_test database."""

from datetime import datetime, timedelta

# ---------- helpers ----------


def create_plan(client, headers, name="Basic", price="10.00"):
    response = client.post("/plans", json={"name": name, "price": price}, headers=headers)
    assert response.status_code == 201
    return response.json()


def create_customer(client, headers, email, card_status="valid"):
    body = {"email": email, "full_name": "Test Person", "card_last4": "4242", "card_status": card_status}
    response = client.post("/customers", json=body, headers=headers)
    assert response.status_code == 201
    return response.json()


def subscribe(client, headers, customer_id, plan_id):
    response = client.post("/subscriptions", json={"customer_id": customer_id, "plan_id": plan_id}, headers=headers)
    assert response.status_code == 201
    return response.json()


def at(subscription, days_after_period_end):
    """A pretend date: N days after the subscription's current period ends."""
    end = datetime.fromisoformat(subscription["current_period_end"])
    return (end + timedelta(days=days_after_period_end)).isoformat()


def run_billing(client, headers, as_of):
    response = client.post("/billing/run", params={"as_of": as_of}, headers=headers)
    assert response.status_code == 200
    return response.json()


def run_retries(client, headers, as_of):
    response = client.post("/billing/retries/run", params={"as_of": as_of}, headers=headers)
    assert response.status_code == 200
    return response.json()


# ---------- security and errors ----------


def test_health_is_open(client):
    assert client.get("/health").json()["status"] == "ok"


def test_requires_login(client):
    response = client.get("/plans")
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "unauthorized"
    assert error["request_id"]


def test_viewer_can_read_but_not_write(client, viewer_headers):
    assert client.get("/plans", headers=viewer_headers).status_code == 200
    response = client.post("/plans", json={"name": "Pro", "price": "25.00"}, headers=viewer_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_plan_validation_and_duplicates(client, admin_headers):
    bad = client.post("/plans", json={"name": "Free", "price": "-5"}, headers=admin_headers)
    assert bad.status_code == 422
    assert bad.json()["error"]["details"][0]["field"] == "price"

    create_plan(client, admin_headers, "Basic")
    duplicate = client.post("/plans", json={"name": "Basic", "price": "10.00"}, headers=admin_headers)
    assert duplicate.status_code == 409


# ---------- billing ----------


def test_billing_success_and_no_double_billing(client, admin_headers):
    plan = create_plan(client, admin_headers, "Pro", "25.00")
    customer = create_customer(client, admin_headers, "ramya@test.com", "valid")
    subscription = subscribe(client, admin_headers, customer["id"], plan["id"])

    first = run_billing(client, admin_headers, at(subscription, 1))
    assert first["billed"] == 1
    assert first["results"][0]["payment"] == "succeeded"
    assert first["results"][0]["subscription_status"] == "active"

    # Running billing again for the same date must not charge anyone twice
    second = run_billing(client, admin_headers, at(subscription, 1))
    assert second["billed"] == 0


def test_failed_payment_recovers_after_card_update(client, admin_headers):
    plan = create_plan(client, admin_headers)
    customer = create_customer(client, admin_headers, "john@test.com", "insufficient_funds")
    subscription = subscribe(client, admin_headers, customer["id"], plan["id"])

    billed = run_billing(client, admin_headers, at(subscription, 1))
    assert billed["results"][0]["payment"] == "failed"
    assert billed["results"][0]["subscription_status"] == "past_due"

    # John adds a working card, and the next retry succeeds
    client.patch(f"/customers/{customer['id']}/card", json={"card_last4": "5555"}, headers=admin_headers)
    retried = run_retries(client, admin_headers, at(subscription, 2))
    assert retried["results"][0]["payment"] == "succeeded"
    assert retried["results"][0]["subscription_status"] == "active"

    invoice_id = billed["results"][0]["invoice_id"]
    attempts = client.get(f"/invoices/{invoice_id}/payments", headers=admin_headers).json()
    assert [a["status"] for a in attempts] == ["failed", "succeeded"]
    assert len({a["idempotency_key"] for a in attempts}) == 2  # every attempt has its own key


def test_subscription_paused_after_all_retries_fail(client, admin_headers):
    plan = create_plan(client, admin_headers)
    customer = create_customer(client, admin_headers, "priya@test.com", "expired")
    subscription = subscribe(client, admin_headers, customer["id"], plan["id"])

    run_billing(client, admin_headers, at(subscription, 1))  # attempt 1 fails
    run_retries(client, admin_headers, at(subscription, 2))  # attempt 2 fails
    run_retries(client, admin_headers, at(subscription, 4))  # attempt 3 fails
    last = run_retries(client, admin_headers, at(subscription, 8))  # attempt 4 fails -> paused

    assert last["results"][0]["attempt_number"] == 4
    assert last["results"][0]["subscription_status"] == "paused"
    assert last["results"][0]["next_retry_at"] is None

    # A paused subscription is never retried again
    assert run_retries(client, admin_headers, at(subscription, 30))["retried"] == 0


# ---------- proration ----------


def test_upgrade_is_prorated(client, admin_headers):
    basic = create_plan(client, admin_headers, "Basic", "10.00")
    pro = create_plan(client, admin_headers, "Pro", "25.00")
    customer = create_customer(client, admin_headers, "upgrade@test.com", "valid")
    subscription = subscribe(client, admin_headers, customer["id"], basic["id"])

    start = datetime.fromisoformat(subscription["current_period_start"])
    end = datetime.fromisoformat(subscription["current_period_end"])
    halfway = (start + (end - start) / 2).isoformat()

    response = client.post(
        f"/subscriptions/{subscription['id']}/change-plan",
        params={"as_of": halfway},
        json={"plan_id": pro["id"]},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["amount_due"] == "7.50"
    assert body["payment"] == "succeeded"
    assert body["new_plan"] == "Pro"