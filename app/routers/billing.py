from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import billing as billing_service
from app.database import get_db
from app.models import Invoice, PaymentAttempt
from app.schemas import InvoiceOut, PaymentAttemptOut

router = APIRouter(tags=["Billing"])


def to_utc(value: datetime | None) -> datetime:
    """Use the given date (treated as UTC), or the real current time if empty."""
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# Endpoint 1: POST /billing/run - bill every subscription whose month has ended
@router.post("/billing/run")
def run_billing(
    as_of: datetime | None = Query(
        default=None,
        description="Pretend date for testing, e.g. 2026-12-04. Empty = real current time.",
    ),
    db: Session = Depends(get_db),
):
    now = to_utc(as_of)
    results = billing_service.run_billing(db, now)
    return {"as_of": now, "billed": len(results), "results": results}



# Endpoint 1b: POST /billing/retries/run - retry failed payments that are due
@router.post("/billing/retries/run")
def run_payment_retries(
    as_of: datetime | None = Query(
        default=None,
        description="Pretend date for testing, e.g. 2026-12-06. Empty = real current time.",
    ),
    db: Session = Depends(get_db),
):
    now = to_utc(as_of)
    results = billing_service.run_retries(db, now)
    return {"as_of": now, "retried": len(results), "results": results}


# Endpoint 2: GET /invoices - list invoices (optionally for one subscription)
@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(subscription_id: int | None = None, db: Session = Depends(get_db)):
    query = select(Invoice).order_by(Invoice.id)
    if subscription_id is not None:
        query = query.where(Invoice.subscription_id == subscription_id)
    return db.scalars(query).all()


# Endpoint 3: GET /invoices/{invoice_id}/payments - every charge try for one invoice
@router.get("/invoices/{invoice_id}/payments", response_model=list[PaymentAttemptOut])
def list_payment_attempts(invoice_id: int, db: Session = Depends(get_db)):
    if db.get(Invoice, invoice_id) is None:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found")
    return db.scalars(
        select(PaymentAttempt)
        .where(PaymentAttempt.invoice_id == invoice_id)
        .order_by(PaymentAttempt.attempt_number)
    ).all()


