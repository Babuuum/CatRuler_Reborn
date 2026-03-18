from datetime import UTC, datetime

import pytest

from app.core.db.models.models import PlanEnum, User
from app.core.jwt import create_access_token


async def _create_user(
    db_session,
    *,
    telegram_id: int,
    text_model_key: str = "or_gemini",
    image_model_key: str = "pollen_flux",
) -> User:
    user = User(
        telegram_id=telegram_id,
        plan=PlanEnum.free,
        extended_free=False,
        api_password_hash=None,
        text_model_key=text_model_key,
        image_model_key=image_model_key,
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_get_me_returns_model_keys(client, db_session):
    user = await _create_user(
        db_session,
        telegram_id=5001,
        text_model_key="hf_qwen",
        image_model_key="hf_sd_spaces",
    )
    token = create_access_token(str(user.id))

    response = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["text_model_key"] == "hf_qwen"
    assert response.json()["image_model_key"] == "hf_sd_spaces"


@pytest.mark.asyncio
async def test_patch_me_updates_model_keys(client, db_session):
    user = await _create_user(db_session, telegram_id=5002)
    token = create_access_token(str(user.id))

    response = await client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text_model_key": "hf_llama",
            "image_model_key": "pollen_turbo",
        },
    )

    assert response.status_code == 200
    assert response.json()["text_model_key"] == "hf_llama"
    assert response.json()["image_model_key"] == "pollen_turbo"


@pytest.mark.asyncio
async def test_patch_me_returns_422_for_invalid_model_key(client, db_session):
    user = await _create_user(db_session, telegram_id=5003)
    token = create_access_token(str(user.id))

    response = await client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"text_model_key": "invalid-model"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_key", "payload_value"),
    [
        ("text_model_key", None),
        ("image_model_key", None),
    ],
)
async def test_patch_me_returns_422_for_null_fields(
    client, db_session, payload_key, payload_value
):
    user = await _create_user(db_session, telegram_id=5004)
    token = create_access_token(str(user.id))

    response = await client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={payload_key: payload_value},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_me_rejects_extended_free_field(client, db_session):
    user = await _create_user(db_session, telegram_id=5005)
    token = create_access_token(str(user.id))

    response = await client.patch(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"extended_free": True},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_models_returns_available_model_keys(client):
    response = await client.get("/models")

    assert response.status_code == 200
    assert response.json() == {
        "text_model_keys": [
            "or_gemini",
            "or_mistral",
            "hf_deepseek",
            "hf_llama",
            "hf_qwen",
            "hf_phi",
        ],
        "image_model_keys": [
            "pollen_flux",
            "pollen_flux_realism",
            "pollen_turbo",
            "hf_sd_spaces",
        ],
    }
