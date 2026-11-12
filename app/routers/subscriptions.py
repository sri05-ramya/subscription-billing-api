from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import attempt_payment
from app.database import get_db
from app.dates import add_one_month
from app.models import Customer, Invoice, Plan, Subscription
from app.proration import prorate
from app.schemas import PlanChangeRequest, SubscriptionCreate, SubscriptionOut

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

# A customer can have only one subscription in these states at a time
OPEN_STATUSES = ("active", "past_due")


def get_subscription_or_404(db: Session, subscription_id: int) -> Subscription:
    subscription = db.get(Subscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id} not found")
    return subscription


# Endpoint 1: POST /subscriptions - subscribe a customer to a plan
@router.post("", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    # Rule 1: the customer must exist
    customer = db.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"Customer {payload.customer_id} not found")

    # Rule 2: the plan must exist and be active
    plan = db.get(Plan, payload.plan_id)
    if plan is None or not plan.is_active:
        raise HTTPException(status_code=404, detail=f"Plan {payload.plan_id} not found")

    # Rule 3: no second open subscription for the same customer
    existing = db.scalar(
        select(Subscription).where(
            Subscription.customer_id == customer.id,
            Subscription.status.in_(OPEN_STATUSES),
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Customer {customer.id} already has an open subscription (id {existing.id})",
        )

    now = datetime.now(timezone.utc)
    subscription = Subscription(
        customer_id=customer.id,
        plan_id=plan.id,
        status="active",
        current_period_start=now,
        current_period_end=add_one_month(now),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


# Endpoint 2: GET /subscriptions - list all subscriptions
@router.get("", response_model=list[SubscriptionOut])
def list_subscriptions(db: Session = Depends(get_db)):
    return db.scalars(select(Subscription).order_by(Subscription.id)).all()


# Endpoint 3: GET /subscriptions/{subscription_id} - get one subscription
@router.get("/{subscription_id}", response_model=SubscriptionOut)
def get_subscription(subscription_id: int, db: Session = Depends(get_db)):
    return get_subscription_or_404(db, subscription_id)


# Endpoint 4: POST /subscriptions/{subscription_id}/cancel - cancel a subscription
@router.post("/{subscription_id}/cancel", response_model=SubscriptionOut)
def cancel_subscription(subscription_id: int, db: Session = Depends(get_db)):
    subscription = get_subscription_or_404(db, subscription_id)
    if subscription.status == "cancelled":
        raise HTTPException(status_code=409, detail="Subscription is already cancelled")

    subscription.status = "cancelled"
    subscription.next_retry_at = None
    db.commit()
    db.refresh(subscription)
    return subscription



# Endpoint 5: POST /subscriptions/{subscription_id}/change-plan - upgrade/downgrade with proration
@router.post("/{subscription_id}/change-plan")
def change_plan(
    subscription_id: int,
    payload: PlanChangeRequest,
    as_of: datetime | None = Query(
        default=None,
        description="Pretend date for testing. Empty = real current time.",
    ),
    db: Session = Depends(get_db),
):
    subscription = get_subscription_or_404(db, subscription_id)
    if subscription.status != "active":
        raise HTTPException(status_code=409, detail="Only active subscriptions can change plan")

    new_plan = db.get(Plan, payload.plan_id)
    if new_plan is None or not new_plan.is_active:
        raise HTTPException(status_code=404, detail=f"Plan {payload.plan_id} not found")

    old_plan = subscription.plan
    if new_plan.id == old_plan.id:
        raise HTTPException(status_code=409, detail="Subscription is already on this plan")

    now = as_of if as_of else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if not (subscription.current_period_start <= now < subscription.current_period_end):
        raise HTTPException(status_code=409, detail="Change date must be inside the current billing period")

    result = prorate(
        old_plan.price,
        new_plan.price,
        subscription.current_period_start,
        subscription.current_period_end,
        now,
    )

    invoice_id = None
    payment = "not_needed"
    if result["amount_due"] > 0:
        invoice = Invoice(
            subscription_id=subscription.id,
            amount=result["amount_due"],
            status="open",
            period_start=now,
            period_end=subscription.current_period_end,
        )
        db.add(invoice)
        db.flush()
        attempt = attempt_payment(db, invoice, now)
        invoice_id = invoice.id
        payment = attempt.status

    subscription.plan = new_plan
    db.commit()

    return {
        "subscription_id": subscription.id,
        "old_plan": old_plan.name,
        "new_plan": new_plan.name,
        "changed_at": now,
        **result,
        "invoice_id": invoice_id,
        "payment": payment,
        "subscription_status": subscription.status,
    }