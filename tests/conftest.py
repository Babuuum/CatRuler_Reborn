# ruff: noqa: E402

import asyncio
from uuid import uuid4

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from tests.database import upgrade_test_database
from tests.environment import configure_test_settings, test_database_url

configure_test_settings()

from app.api.dependencies.db import get_db
from app.api.main import app


@pytest_asyncio.fixture
async def postgres_database():
    """An empty, uniquely named database owned by this test, including teardown."""
    admin_url = test_database_url()
    admin = await asyncpg.connect(
        admin_url.set(drivername="postgresql").render_as_string(hide_password=False),
        timeout=5,
        command_timeout=10,
    )
    database_name = f"catruler_test_{uuid4().hex}"
    created = False
    try:
        # Identifier is generated locally, never supplied by a caller.
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        created = True
        yield admin_url.set(database=database_name).render_as_string(
            hide_password=False
        )
    finally:
        try:
            if created:
                await admin.execute(f'DROP DATABASE "{database_name}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest_asyncio.fixture
async def db_engine(postgres_database) -> AsyncEngine:
    await asyncio.to_thread(upgrade_test_database, postgres_database)
    engine = create_async_engine(postgres_database, poolclass=NullPool)
    try:
        yield engine
    finally:
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

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
