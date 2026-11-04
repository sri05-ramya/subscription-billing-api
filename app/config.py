from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    app_name: str = "Subscription Billing API"
    environment: str = "local"

    # Database
    database_url: str = "sqlite:///./billing.db"

    # Login tokens (JWT)
    jwt_secret: str = "change-me-to-a-long-random-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30

    # Billing rules
    max_payment_retries: int = 3
    retry_days: str = "1,3,7"

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()