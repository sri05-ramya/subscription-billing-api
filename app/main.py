from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": settings.environment,
        "max_payment_retries": settings.max_payment_retries,
    }