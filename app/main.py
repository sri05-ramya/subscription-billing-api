from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app import models  # noqa: F401  (loads the tables so Base knows about them)
from app.config import get_settings
from app.database import Base, engine
from app.routers import auth, billing, customers, plans, subscriptions
from app.deps import staff_access
from app.logging_config import setup_logging
from app.middleware import RequestContextMiddleware
from app.errors import register_error_handlers

settings = get_settings()
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the app starts
    Base.metadata.create_all(bind=engine)
    yield
    # Code after yield would run when the app stops


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
register_error_handlers(app)
app.include_router(auth.router)
app.include_router(plans.router, dependencies=[Depends(staff_access)])
app.include_router(customers.router, dependencies=[Depends(staff_access)])
app.include_router(subscriptions.router, dependencies=[Depends(staff_access)])
app.include_router(billing.router, dependencies=[Depends(staff_access)])


@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": settings.environment,
        "max_payment_retries": settings.max_payment_retries,
    }