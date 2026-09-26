from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "MedSlot API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Database connection URL
    DATABASE_URL: str = "sqlite+aiosqlite:///./medslot.db"

    # JWT Authentication
    SECRET_KEY: str = "medslot-development-secret-key-32-chars-minimum-length-eve"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Redis Cache (Optional bonus)
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"

    # Webhook Security
    PAYMENT_WEBHOOK_SECRET: str = "whsec_medslot_mock_secret_key"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url


@lru_cache()
def get_settings() -> Settings:
    return Settings()
