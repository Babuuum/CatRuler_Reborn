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

    # TG
    TELEGRAM_BOT_TOKEN: str = ""
    INTERNAL_API_URL: str = "http://localhost:8000"
    BASE_URL: str = ""
    WEBHOOK_PATH: str = ""
    TELEGRAM_BOT_SECRET_TOKEN: str = ""

    # LLM
    OPEN_ROUTER_API_KEY: str = ""
    HUGGING_FACE_API_KEY: str = ""
    POLLEN_API_KEY: str = ""

    # YANDEX_STORAGE
    YANDEX_ACCESS_KEY: str = ""
    YANDEX_SECRET_KEY: str = ""
    YANDEX_BUCKET_NAME: str = ""

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
        return f"postgresql+asyncpg://{self.PROD_DB_USER}:{self.PROD_DB_PASSWORD}@{self.PROD_DB_HOST}:{self.PROD_DB_PORT}/{self.PROD_DB_NAME}"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
