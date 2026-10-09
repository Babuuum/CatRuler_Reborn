"""Explicit test settings; never load a dotenv file or inherited app credentials."""

import os

from cryptography.fernet import Fernet
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from app.core import settings as settings_module

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://catruler_test@127.0.0.1:55432/catruler_test"
)


def test_database_url() -> URL:
    raw_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    try:
        url = make_url(raw_url)
        valid = (
            url.drivername == "postgresql+asyncpg"
            and url.host in {"127.0.0.1", "localhost", "::1"}
            and url.username == "catruler_test"
            and url.database == "catruler_test"
            and url.port is not None
            and not url.query
        )
    except (ArgumentError, ValueError, TypeError):
        valid = False
    if not valid:
        raise RuntimeError(
            "TEST_DATABASE_URL must target a local PostgreSQL instance with "
            "the dedicated catruler_test role/database and an explicit port"
        ) from None
    return url


def configure_test_settings() -> None:
    settings_class = settings_module.Settings
    # Also protect later Settings() calls (including migration imports).
    settings_class.model_config["env_file"] = None
    values = {
        name: field.default
        for name, field in settings_class.model_fields.items()
        if not field.is_required()
    }
    values.update(
        DATABASE_URL=test_database_url().render_as_string(hide_password=False),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        JWT_SECRET_KEY="test-only-jwt-secret",
        INTERNAL_API_SHARED_SECRET="test-only-internal-secret",
        REDIS_URL="redis://127.0.0.1:1/0",
        CELERY_BROKER_URL="memory://",
        CELERY_RESULT_BACKEND="cache+memory://",
        INTERNAL_API_URL="http://test.invalid",
    )
    # Remove case variants too: Settings is case-insensitive.
    field_names = set(settings_class.model_fields)
    for name in list(os.environ):
        if name.upper() in field_names:
            del os.environ[name]
    for name, value in values.items():
        os.environ[name] = str(value)
    settings_module._settings = settings_class(_env_file=None, **values)
