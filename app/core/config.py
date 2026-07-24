from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # MongoDB — replica set required for ACID transactions
    MONGO_URI: str = "mongodb://localhost:27017/?replicaSet=rs0"
    MONGO_DB_NAME: str = "vnpt_ai_performance"
    MONGO_REPLICA_SET: str = "rs0"

    # Application
    APP_NAME: str = "AI Workforce Management"
    DEBUG: bool = False
    CORS_ALLOWED_ORIGINS: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    # JWT. Access tokens are deliberately short-lived; refresh tokens are
    # rotated and backed by a revocable MongoDB session record.
    JWT_SECRET_KEY: str = "change-me-to-a-long-random-secret"
    JWT_REFRESH_SECRET_KEY: str = "change-me-to-a-different-long-random-secret"
    JWT_ALGORITHM: str = "HS256"
    # Deprecated compatibility field; no longer used by the cookie auth flow.
    JWT_EXPIRE_MINUTES: int | None = None
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "vnpt-workforce-api"
    JWT_AUDIENCE: str = "vnpt-workforce-web"

    # Cookie/CSRF. Secure must stay true outside isolated HTTP development.
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: Literal["strict"] = "strict"
    CSRF_SECRET_KEY: str = "change-me-to-an-independent-csrf-secret"

    # Internal cron job auth
    CRON_SECRET_KEY: str = "change-me-internal-cron-secret"
    INTERNAL_CRON_SECRET: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
