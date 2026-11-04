from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer
from app.schemas import CustomerCardUpdate, CustomerCreate, CustomerOut

router = APIRouter(prefix="/customers", tags=["Customers"])


def get_customer_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return customer


# Endpoint 1: POST /customers - create a customer
@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Customer).where(Customer.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="A customer with this email already exists")

    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


# Endpoint 2: GET /customers - list all customers
@router.get("", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    return db.scalars(select(Customer).order_by(Customer.id)).all()


# Endpoint 3: GET /customers/{customer_id} - get one customer
@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    return get_customer_or_404(db, customer_id)


# Endpoint 4: PATCH /customers/{customer_id}/card - update the card
@router.patch("/{customer_id}/card", response_model=CustomerOut)
def update_card(customer_id: int, payload: CustomerCardUpdate, db: Session = Depends(get_db)):
    customer = get_customer_or_404(db, customer_id)
    customer.card_last4 = payload.card_last4
    customer.card_status = payload.card_status
    db.commit()
    db.refresh(customer)
    return customer