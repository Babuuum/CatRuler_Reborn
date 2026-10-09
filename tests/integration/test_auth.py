from datetime import UTC, datetime

import bcrypt
import pytest

from app.core.db.models.models import PlanEnum, User
from app.core.jwt import create_access_token


async def _create_user(
    db_session,
    *,
    telegram_id: int,
    api_password_hash: str | None,
) -> User:
    user = User(
        telegram_id=telegram_id,
        plan=PlanEnum.free,
        extended_free=False,
        api_password_hash=api_password_hash,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_login_returns_401_if_user_not_found(client):
    response = await client.post(
        "/auth/login",
        json={"telegram_id": 999999, "password": "secret"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_returns_401_if_password_incorrect(client, db_session):
    password_hash = bcrypt.hashpw(b"correct", bcrypt.gensalt()).decode()
    await _create_user(
        db_session,
        telegram_id=1001,
        api_password_hash=password_hash,
    )

    response = await client.post(
        "/auth/login",
        json={"telegram_id": 1001, "password": "wrong"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_returns_401_if_api_password_not_set(client, db_session):
    await _create_user(db_session, telegram_id=1002, api_password_hash=None)

    response = await client.post(
        "/auth/login",
        json={"telegram_id": 1002, "password": "secret"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_returns_token_on_success(client, db_session):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
    await _create_user(
        db_session,
        telegram_id=1003,
        api_password_hash=password_hash,
    )

    response = await client.post(
        "/auth/login",
        json={"telegram_id": 1003, "password": "secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body


@pytest.mark.asyncio
async def test_get_me_returns_401_without_token(client):
    response = await client.get("/users/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_returns_401_with_invalid_token(client):
    response = await client.get(
        "/users/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_returns_200_with_valid_token(client, db_session):
    user = await _create_user(db_session, telegram_id=2001, api_password_hash=None)
    token = create_access_token(str(user.id))

    response = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


async def test_generated_api_password_uses_real_bcrypt_and_logs_in(client, db_session):
    from sqlalchemy import select

    from app.core.settings import get_settings

    response = await client.post(
        "/users/me/api-password",
        headers={
            "X-Telegram-Id": "2002",
            "X-Internal-Api-Secret": get_settings().INTERNAL_API_SHARED_SECRET,
        },
    )
    assert response.status_code == 200
    password = response.json()["password"]
    user = (
        await db_session.execute(select(User).where(User.telegram_id == 2002))
    ).scalar_one()
    assert user.api_password_hash.startswith("$2b$")
    assert bcrypt.checkpw(password.encode(), user.api_password_hash.encode())
    assert not bcrypt.checkpw(b"wrong-password", user.api_password_hash.encode())
    login = await client.post(
        "/auth/login", json={"telegram_id": 2002, "password": password}
    )
    assert login.status_code == 200
