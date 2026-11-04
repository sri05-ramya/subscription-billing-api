from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dates import add_one_month
from app.models import Customer, Plan, Subscription
from app.schemas import SubscriptionCreate, SubscriptionOut

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