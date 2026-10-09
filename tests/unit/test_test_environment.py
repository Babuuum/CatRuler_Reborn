import pytest

from app.core import settings as settings_module
from tests.environment import configure_test_settings
from tests.environment import test_database_url as database_url


@pytest.mark.parametrize(
    "value",
    [
        "invalid",
        "sqlite:///catruler_test",
        "postgresql+asyncpg://catruler_test@db.example:5432/catruler_test",
        "postgresql+asyncpg://catruler_test@localhost:5432/production",
        "postgresql+asyncpg://postgres@localhost:5432/catruler_test",
        "postgresql+asyncpg://catruler_test@localhost:5432/catruler_test?host=db.example",
    ],
)
def test_database_guard_rejects_unsafe_targets(monkeypatch, value):
    monkeypatch.setenv("TEST_DATABASE_URL", value)
    with pytest.raises(RuntimeError, match="dedicated catruler_test"):
        database_url()


def test_bootstrap_overrides_inherited_settings_and_disables_dotenv(monkeypatch):
    import os

    from pydantic_settings import DotEnvSettingsSource

    def forbid_dotenv_reads(source):
        assert source.env_file is None, "Tests attempted to read a dotenv file"
        return {}

    monkeypatch.setattr(DotEnvSettingsSource, "_read_env_files", forbid_dotenv_reads)
    # Keep the original process configuration for the other tests.
    monkeypatch.setattr(settings_module, "_settings", settings_module._settings)
    monkeypatch.setattr(
        settings_module.Settings,
        "model_config",
        {**settings_module.Settings.model_config, "env_file": ".env"},
    )
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://invalid/production")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "inherited-placeholder")
    monkeypatch.setenv("YANDEX_ACCESS_KEY", "inherited-placeholder")
    monkeypatch.setenv("jwt_secret_key", "inherited-placeholder")
    configure_test_settings()
    settings = settings_module.get_settings()
    assert settings.TELEGRAM_BOT_TOKEN == ""
    assert settings.YANDEX_ACCESS_KEY == ""
    assert "production" not in settings.database_url
    assert settings.JWT_SECRET_KEY == "test-only-jwt-secret"
    assert settings_module.Settings.model_config["env_file"] is None
    assert settings_module.Settings().TELEGRAM_BOT_TOKEN == ""


def test_migration_runner_rejects_admin_database():
    from tests.database import upgrade_test_database

    with pytest.raises(RuntimeError, match="fixture-created"):
        upgrade_test_database(database_url().render_as_string(hide_password=False))
