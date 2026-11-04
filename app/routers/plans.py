from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Plan
from app.schemas import PlanCreate, PlanOut

router = APIRouter(prefix="/plans", tags=["Plans"])


@router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Plan).where(Plan.name == payload.name))
    if existing:
        raise HTTPException(status_code=409, detail=f"Plan '{payload.name}' already exists")

    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    return db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price)).all()


@router.get("/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return plan