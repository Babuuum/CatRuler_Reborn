from cryptography.fernet import Fernet
from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PROJECT
    DEV_MODE: bool = True
    LOG_LEVEL: str = "INFO"
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    # DB
    PROD_DB_NAME: str = ""
    PROD_DB_USER: str = ""
    PROD_DB_PASSWORD: str = ""
    PROD_DB_HOST: str = ""
    PROD_DB_PORT: str = ""
    DATABASE_URL: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # TG
    TELEGRAM_BOT_TOKEN: str = ""
    INTERNAL_API_URL: str = "http://localhost:8000"
    BOT_MODE: str = "polling"
    WEBHOOK_BASE_URL: str = ""
    WEBHOOK_PATH: str = "/webhook/bot"
    WEBHOOK_SECRET: str = ""
    BASE_URL: str = ""
    TELEGRAM_BOT_SECRET_TOKEN: str = ""

    # LLM
    OPEN_ROUTER_API_KEY: str = ""
    HUGGING_FACE_API_KEY: str = ""
    POLLEN_API_KEY: str = ""

    # YANDEX_STORAGE
    YANDEX_ACCESS_KEY: str = ""
    YANDEX_SECRET_KEY: str = ""
    YANDEX_BUCKET_NAME: str = ""
    PUBLISH_REQUEST_TIMEOUT: float = 60.0

    # CRYPTO
    ENCRYPTION_KEY: str

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        try:
            Fernet(v.encode())
        except Exception:
            raise ValueError("ENCRYPTION_KEY must be a valid Fernet key")
        return v

    @computed_field
    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.PROD_DB_USER}:{self.PROD_DB_PASSWORD}@{self.PROD_DB_HOST}:{self.PROD_DB_PORT}/{self.PROD_DB_NAME}"

    @computed_field
    @property
    def sync_database_url(self) -> str:
        if self.database_url.startswith("sqlite+aiosqlite://"):
            return self.database_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
        if self.database_url.startswith("postgresql+asyncpg://"):
            return self.database_url.replace(
                "postgresql+asyncpg://", "postgresql://", 1
            )
        return self.database_url

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
