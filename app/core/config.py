from functools import lru_cache

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

    # JWT
    JWT_SECRET_KEY: str = "change-me-to-a-long-random-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    # Internal cron job auth
    CRON_SECRET_KEY: str = "change-me-internal-cron-secret"
    INTERNAL_CRON_SECRET: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
