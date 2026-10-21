from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфиг сервиса. Читается из env или .env."""

    APP_NAME: str = "Payment Service"
    DEBUG: bool = False

    API_KEY: str = "test-api-key-12345"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/payments_db"

    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    OUTBOX_POLL_INTERVAL: float = 1.0

    PAYMENT_MIN_DELAY: int = 2
    PAYMENT_MAX_DELAY: int = 5
    PAYMENT_SUCCESS_RATE: float = 0.9

    WEBHOOK_MAX_RETRIES: int = 3
    WEBHOOK_RETRY_BASE_DELAY: float = 1.0

    MAX_PROCESSING_RETRIES: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Настройки читаются один раз за жизнь процесса."""
    return Settings()
