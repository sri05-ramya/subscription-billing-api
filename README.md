# Subscription Billing & Failed-Payment Recovery API

A backend service that bills customers every month, retries failed card payments on a smart schedule, never charges anyone twice, and prorates plan changes mid-month.

Built with **FastAPI, PostgreSQL, SQLAlchemy, Pydantic, JWT and Docker**.

---

## The problem

Subscription businesses (streaming, SaaS, memberships) charge customers every month. That sounds simple, but:

- **Cards fail.** Expired cards and insufficient funds cause lost revenue and lost customers.
- **Retrying badly hurts.** Retrying too fast looks like fraud; never retrying loses money.
- **Double charges happen.** A network glitch can send the same charge twice.
- **Plan changes are tricky.** Upgrading mid-month should cost only the difference for the days left.

## What this API does

| Feature | How it works |
|---|---|
| Monthly billing | Finds subscriptions whose period has ended, creates the invoice and charges the card |
| Failed-payment retries | Retries on day 1, 3 and 7 (configurable), then pauses the subscription |
| Recovery | If the customer updates their card, the next retry succeeds and the subscription is active again |
| No double charging | Unique idempotency key per charge attempt, plus a database constraint of one invoice per subscription per period |
| Proration | Upgrade halfway through the month: pay only the difference for the remaining time |
| Correct month math | Jan 31 + 1 month = Feb 28/29 |
| Security | JWT login, PBKDF2-hashed passwords, role-based access (viewer reads, admin writes) |
| Observability | JSON logs with a request ID on every line, plus timing and slow-request warnings |
| Consistent errors | Every error uses one shape: `{"error": {code, message, details, request_id}}` |

## Subscription lifecycle

```
active ──payment fails──► past_due ──retry succeeds──► active
                              │
                              └──all retries fail──► paused
active / past_due ──customer cancels──► cancelled
```

## Tech stack

- **API:** FastAPI, Pydantic v2
- **Database:** PostgreSQL 16, SQLAlchemy 2.0
- **Auth:** JWT (PyJWT), PBKDF2-SHA256 password hashing
- **Testing:** pytest (unit tests + API tests against a separate test database)
- **DevOps:** Docker, docker-compose

## Project structure

```
app/
├── main.py             # app setup, routers, middleware
├── config.py           # settings from environment variables
├── database.py         # engine and session
├── models.py           # tables: plans, customers, subscriptions, invoices, payment_attempts, users
├── schemas.py          # request/response validation
├── billing.py          # billing service: invoices, charges, retries
├── proration.py        # plan-change math (pure function)
├── dates.py            # add-one-month helper
├── payment_gateway.py  # fake gateway (swap for Stripe in production)
├── security.py         # password hashing, JWT
├── deps.py             # login and role checks
├── middleware.py       # request ID, timing, access log
├── errors.py           # consistent error responses
├── logging_config.py   # JSON logging
└── routers/            # auth, plans, customers, subscriptions, billing
scripts/create_admin.py # create a staff user from the terminal
tests/                  # unit and API tests
```

## Run with Docker (easiest)

```bash
docker compose up --build -d
docker compose exec api python -m scripts.create_admin
```

Open **http://localhost:8080/docs**, log in with **POST /auth/login**, click **Authorize** and paste the token.

## Run locally

```bash
python -m venv venv
venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # then set DATABASE_URL and JWT_SECRET
python -m scripts.create_admin
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs**.

## Run the tests

Create an empty PostgreSQL database named `<your database>_test` (for example `billing_test`), then:

```bash
pytest -v
```

21 tests cover month math, proration, the payment gateway, password hashing, login and roles, validation errors, billing, no double billing, recovery after a card update, pausing after the final retry, and prorated upgrades.

## Try the billing flow

Billing endpoints accept an optional `as_of` date, so you can "time travel" without waiting a month:

1. Create plans and customers (use `card_status: "insufficient_funds"` to simulate a failing card).
2. Subscribe a customer.
3. `POST /billing/run?as_of=<one month later>` creates invoices and charges cards.
4. `POST /billing/retries/run?as_of=<a few days later>` retries failed payments.
5. `PATCH /customers/{id}/card` updates the card, and the next retry recovers the subscription.

## Main endpoints

| Method | Endpoint | Access |
|---|---|---|
| POST | `/auth/login` | Public |
| GET | `/auth/me` | Logged in |
| GET/POST | `/plans` | Read: staff · Write: admin |
| GET/POST | `/customers` · PATCH `/customers/{id}/card` | Read: staff · Write: admin |
| GET/POST | `/subscriptions` · `/cancel` · `/change-plan` | Read: staff · Write: admin |
| POST | `/billing/run` · `/billing/retries/run` | Admin |
| GET | `/invoices` · `/invoices/{id}/payments` | Staff |
| GET | `/health` | Public |

## Design decisions

- **Money uses `Decimal`/`NUMERIC(10,2)`**, never floats, so there are no rounding errors.
- **All timestamps are stored in UTC** to avoid time-zone and daylight-saving bugs.
- **Business logic lives in services** (`billing.py`, `proration.py`), not in endpoints, so it's reusable and testable.
- **The payment gateway is isolated** in one module, so a real provider like Stripe can replace it without touching billing logic.
- **Protection is applied per router**, so new endpoints are secured by default.

## Future improvements

- Apply downgrade credit to the next invoice
- Send email reminders after failed payments
- Run billing and retries on a scheduler (cron or Celery)
- Database migrations with Alembic
- Integrate a real payment provider (Stripe test mode)