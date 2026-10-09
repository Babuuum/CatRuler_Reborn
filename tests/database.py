"""Migration runner for databases created by the PostgreSQL test fixture."""

import os
import re
from pathlib import Path

from sqlalchemy.engine import make_url

from alembic import command
from alembic.config import Config
from tests.environment import test_database_url


def alembic_config() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


def upgrade_test_database(database_url: str, revision: str = "head") -> None:
    """Run in a worker thread: the existing Alembic env owns its event loop."""
    url = make_url(database_url)
    admin_url = test_database_url()
    if (
        not re.fullmatch(r"catruler_test_[0-9a-f]{32}", url.database or "")
        or url.set(database=admin_url.database) != admin_url
    ):
        raise RuntimeError("Migrations may only target a fixture-created test database")
    previous_url = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(alembic_config(), revision)
    finally:
        os.environ["DATABASE_URL"] = previous_url
