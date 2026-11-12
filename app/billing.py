"""Billing service: create invoices, charge cards, and schedule retries."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dates import add_one_month
from app.models import Invoice, PaymentAttempt, Subscription
from app.payment_gateway import charge_card

logger = logging.getLogger("app.billing")


def retry_days() -> list[int]:
    """'1,3,7' from .env -> [1, 3, 7], limited to MAX_PAYMENT_RETRIES."""
    settings = get_settings()
    days = [int(d) for d in settings.retry_days.split(",") if d.strip()]
    return days[: settings.max_payment_retries]


# Job 1: make a new bill for one month
def create_invoice(
    db: Session, subscription: Subscription, period_start: datetime, period_end: datetime
) -> Invoice:
    invoice = Invoice(
        subscription_id=subscription.id,
        amount=subscription.plan.price,
        status="open",
        period_start=period_start,
        period_end=period_end,
    )
    db.add(invoice)
    db.flush()  # sends it to the database now, so we get invoice.id
    return invoice


# Job 2: try to charge the card, save the try, and update statuses
def attempt_payment(db: Session, invoice: Invoice, now: datetime) -> PaymentAttempt:
    subscription = invoice.subscription
    customer = subscription.customer

    previous_attempts = db.scalar(
        select(func.count()).select_from(PaymentAttempt).where(PaymentAttempt.invoice_id == invoice.id)
    ) or 0
    attempt_number = previous_attempts + 1
    idempotency_key = f"invoice-{invoice.id}-attempt-{attempt_number}"

    result = charge_card(customer.card_status, invoice.amount, idempotency_key)

    attempt = PaymentAttempt(
        invoice_id=invoice.id,
        attempt_number=attempt_number,
        amount=invoice.amount,
        status="succeeded" if result.succeeded else "failed",
        failure_reason=result.failure_reason,
        idempotency_key=idempotency_key,
    )
    db.add(attempt)

    if result.succeeded:
        logger.info(
            "payment succeeded",
            extra={
                "invoice_id": invoice.id,
                "subscription_id": subscription.id,
                "attempt_number": attempt_number,
                "amount": str(invoice.amount),
            },
        )
        invoice.status = "paid"
        invoice.paid_at = now
        subscription.status = "active"
        subscription.retry_count = 0
        subscription.next_retry_at = None
        return attempt

    # The charge failed: schedule the next retry, or pause if none are left
    schedule = retry_days()
    retries_done = attempt_number - 1
    subscription.retry_count = retries_done
    if retries_done < len(schedule):
        subscription.status = "past_due"
        subscription.next_retry_at = invoice.period_start + timedelta(days=schedule[retries_done])
        logger.warning(
            "payment failed, retry scheduled",
            extra={
                "invoice_id": invoice.id,
                "subscription_id": subscription.id,
                "attempt_number": attempt_number,
                "reason": result.failure_reason,
                "next_retry_at": subscription.next_retry_at,
            },
        )
    else:
        invoice.status = "failed"
        subscription.status = "paused"
        subscription.next_retry_at = None
        logger.error(
            "subscription paused after final retry",
            extra={
                "invoice_id": invoice.id,
                "subscription_id": subscription.id,
                "attempt_number": attempt_number,
                "reason": result.failure_reason,
            },
        )
    return attempt


# Job 3: bill every active subscription whose month has ended
def run_billing(db: Session, now: datetime) -> list[dict]:
    due = db.scalars(
        select(Subscription)
        .where(Subscription.status == "active", Subscription.current_period_end <= now)
        .order_by(Subscription.id)
    ).all()

    results = []
    for subscription in due:
        new_start = subscription.current_period_end
        new_end = add_one_month(new_start)

        invoice = create_invoice(db, subscription, new_start, new_end)
        subscription.current_period_start = new_start
        subscription.current_period_end = new_end

        attempt = attempt_payment(db, invoice, now)
        results.append(
            {
                "subscription_id": subscription.id,
                "invoice_id": invoice.id,
                "amount": str(invoice.amount),
                "payment": attempt.status,
                "failure_reason": attempt.failure_reason,
                "subscription_status": subscription.status,
                "next_retry_at": subscription.next_retry_at,
            }
        )

    db.commit()
    return results


# Job 4: retry failed payments whose retry time has come
def run_retries(db: Session, now: datetime) -> list[dict]:
    due = db.scalars(
        select(Subscription)
        .where(Subscription.status == "past_due", Subscription.next_retry_at <= now)
        .order_by(Subscription.id)
    ).all()

    results = []
    for subscription in due:
        invoice = db.scalar(
            select(Invoice)
            .where(Invoice.subscription_id == subscription.id, Invoice.status == "open")
            .order_by(Invoice.period_start.desc())
            .limit(1)
        )
        if invoice is None:
            continue

        attempt = attempt_payment(db, invoice, now)
        results.append(
            {
                "subscription_id": subscription.id,
                "invoice_id": invoice.id,
                "attempt_number": attempt.attempt_number,
                "payment": attempt.status,
                "failure_reason": attempt.failure_reason,
                "subscription_status": subscription.status,
                "retry_count": subscription.retry_count,
                "next_retry_at": subscription.next_retry_at,
            }
        )

    db.commit()
    return results