# ruff: noqa: E402

import os
import sys
from types import SimpleNamespace

import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# Configure settings before importing app modules that call get_settings() at import time.
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("PROD_DB_NAME", "test")
os.environ.setdefault("PROD_DB_USER", "test")
os.environ.setdefault("PROD_DB_PASSWORD", "test")
os.environ.setdefault("PROD_DB_HOST", "localhost")
os.environ.setdefault("PROD_DB_PORT", "5432")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

# auth_service imports bcrypt at module import time; provide a lightweight test stub
# when bcrypt is absent in environment.
if "bcrypt" not in sys.modules:
    sys.modules["bcrypt"] = SimpleNamespace(
        gensalt=lambda: b"",
        hashpw=lambda password, salt: b"fake$" + password,
        checkpw=lambda password, password_hash: password_hash == b"fake$" + password,
    )

from app.api.dependencies.db import get_db
from app.api.main import app
from app.core.db.base import Base
from app.core.db.models import models as _models  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_engine() -> AsyncEngine:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_maker(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_maker: async_sessionmaker[AsyncSession]) -> AsyncSession:
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_maker: async_sessionmaker[AsyncSession]):
    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
