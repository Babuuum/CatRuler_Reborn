import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.db.models.models import PlanEnum
from app.services import user_service


@pytest.mark.asyncio
async def test_generate_api_password_returns_plain_and_stores_hash(mocker, monkeypatch):
    user_id = uuid4()
    db = object()

    fake_bcrypt = SimpleNamespace(
        gensalt=lambda: b"salt",
        hashpw=lambda password, salt: b"hashed-value",
    )
    monkeypatch.setitem(sys.modules, "bcrypt", fake_bcrypt)

    update_mock = mocker.patch.object(user_service.user_repo, "update")
    mocker.patch.object(user_service, "_generate_password", return_value="PlainPass123")

    result = await user_service.generate_api_password(db, user_id)

    assert result == "PlainPass123"
    update_mock.assert_awaited_once_with(
        db,
        user_id,
        {"api_password_hash": "hashed-value"},
    )


@pytest.mark.asyncio
async def test_generate_api_password_sets_has_api_password_true(mocker, monkeypatch):
    user_id = uuid4()
    db = object()
    now = datetime.now(UTC)

    state = {"api_password_hash": None}

    fake_bcrypt = SimpleNamespace(
        gensalt=lambda: b"salt",
        hashpw=lambda password, salt: b"hash-after-generate",
    )
    monkeypatch.setitem(sys.modules, "bcrypt", fake_bcrypt)

    async def fake_update(_db, _user_id, data):
        state["api_password_hash"] = data["api_password_hash"]
        return SimpleNamespace()

    async def fake_get_by_id(_db, _user_id):
        return SimpleNamespace(
            id=user_id,
            telegram_id=123,
            plan=PlanEnum.free,
            extended_free=False,
            api_password_hash=state["api_password_hash"],
            created_at=now,
        )

    mocker.patch.object(user_service.user_repo, "update", side_effect=fake_update)
    mocker.patch.object(user_service.user_repo, "get_by_id", side_effect=fake_get_by_id)
    mocker.patch.object(user_service, "_generate_password", return_value="Generated123")

    await user_service.generate_api_password(db, user_id)
    response = await user_service.get_me(db, user_id)

    assert response.has_api_password is True


@pytest.mark.asyncio
async def test_generate_api_password_twice_overwrites_old_hash(mocker, monkeypatch):
    user_id = uuid4()
    db = object()
    stored_hashes: list[str] = []

    fake_bcrypt = SimpleNamespace(
        gensalt=lambda: b"salt",
        hashpw=lambda password, salt: f"hash-{password.decode()}".encode(),
    )
    monkeypatch.setitem(sys.modules, "bcrypt", fake_bcrypt)

    async def fake_update(_db, _user_id, data):
        stored_hashes.append(data["api_password_hash"])
        return SimpleNamespace()

    mocker.patch.object(user_service.user_repo, "update", side_effect=fake_update)
    mocker.patch.object(
        user_service, "_generate_password", side_effect=["first", "second"]
    )

    await user_service.generate_api_password(db, user_id)
    await user_service.generate_api_password(db, user_id)

    assert stored_hashes[-1] != stored_hashes[0]


@pytest.mark.asyncio
async def test_get_me_returns_user_response_with_expected_fields(mocker):
    user_id = uuid4()
    created_at = datetime.now(UTC)
    user = SimpleNamespace(
        id=user_id,
        telegram_id=777,
        plan=PlanEnum.base,
        extended_free=True,
        api_password_hash=None,
        created_at=created_at,
    )

    mocker.patch.object(user_service.user_repo, "get_by_id", return_value=user)

    result = await user_service.get_me(object(), user_id)

    assert result.model_dump() == {
        "id": user_id,
        "telegram_id": 777,
        "plan": PlanEnum.base,
        "extended_free": True,
        "has_api_password": False,
        "created_at": created_at,
    }


@pytest.mark.asyncio
async def test_get_me_has_api_password_true_when_hash_exists(mocker):
    user_id = uuid4()
    user = SimpleNamespace(
        id=user_id,
        telegram_id=888,
        plan=PlanEnum.free,
        extended_free=False,
        api_password_hash="some-hash",
        created_at=datetime.now(UTC),
    )

    mocker.patch.object(user_service.user_repo, "get_by_id", return_value=user)

    result = await user_service.get_me(object(), user_id)

    assert result.has_api_password is True
