import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

class StrictRequest(BaseModel):
    """Base for incoming data: unknown fields are rejected, extra spaces trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------- Plans ----------


class PlanCreate(StrictRequest):
    name: str = Field(min_length=1, max_length=50, examples=["Pro"])
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2, examples=["25.00"])
    billing_period: Literal["monthly"] = "monthly"


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: Decimal
    billing_period: str
    is_active: bool
    created_at: datetime



# ---------- Customers ----------

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
CardStatus = Literal["valid", "insufficient_funds", "expired"]


class CustomerCreate(StrictRequest):
    email: str = Field(max_length=254, examples=["ramya@example.com"])
    full_name: str = Field(min_length=1, max_length=120, examples=["Ramya S"])
    card_last4: str = Field(pattern=r"^\d{4}$", examples=["4242"])
    card_status: CardStatus = "valid"

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        if not EMAIL_PATTERN.match(value):
            raise ValueError("must be a valid email address")
        return value.lower()


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    card_last4: str
    card_status: str
    created_at: datetime



class CustomerCardUpdate(StrictRequest):
    card_last4: str = Field(pattern=r"^\d{4}$", examples=["1111"])
    card_status: CardStatus = "valid"



# ---------- Subscriptions ----------


class SubscriptionCreate(StrictRequest):
    customer_id: int = Field(gt=0, examples=[1])
    plan_id: int = Field(gt=0, examples=[1])


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    plan_id: int
    status: str
    current_period_start: datetime
    current_period_end: datetime
    retry_count: int
    next_retry_at: datetime | None
    created_at: datetime


# ---------- Invoices & payments ----------


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscription_id: int
    amount: Decimal
    status: str
    period_start: datetime
    period_end: datetime
    paid_at: datetime | None
    created_at: datetime


class PaymentAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    attempt_number: int
    amount: Decimal
    status: str
    failure_reason: str | None
    idempotency_key: str
    created_at: datetime