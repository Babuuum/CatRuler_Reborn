from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.channel import VKChannelCreate
from app.services import channel_service


@pytest.mark.asyncio
async def test_delete_channel_returns_403_for_other_user(mocker):
    user_id = uuid4()
    channel_id = uuid4()
    foreign_channel = SimpleNamespace(id=channel_id, user_id=uuid4())

    mocker.patch.object(
        channel_service.channel_repo,
        "get_by_id_for_update",
        return_value=foreign_channel,
    )

    with pytest.raises(HTTPException) as exc_info:
        await channel_service.delete_channel(object(), user_id, channel_id)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_channel_succeeds_for_owner(mocker):
    db = object()
    user_id = uuid4()
    channel_id = uuid4()
    owned_channel = SimpleNamespace(id=channel_id, user_id=user_id)

    mocker.patch.object(
        channel_service.channel_repo,
        "get_by_id_for_update",
        return_value=owned_channel,
    )
    mocker.patch.object(
        channel_service.channel_repo, "has_active_publish_attempt", return_value=False
    )
    update_mock = mocker.patch.object(
        channel_service.channel_repo, "update", return_value=owned_channel
    )

    await channel_service.delete_channel(db, user_id, channel_id)

    update_mock.assert_awaited_once_with(db, channel_id, {"is_active": False})


@pytest.mark.asyncio
async def test_create_vk_channel_returns_403_if_plan_limit_exceeded(mocker):
    user_id = uuid4()
    data = VKChannelCreate(name="VK", group_id="123", community_token="token")

    mocker.patch.object(
        channel_service,
        "_check_plan_limit",
        side_effect=HTTPException(status_code=403, detail="Channel limit reached"),
    )
    create_vk_mock = mocker.patch.object(channel_service.channel_repo, "create_vk")

    with pytest.raises(HTTPException) as exc_info:
        await channel_service.create_vk_channel(object(), user_id, data)

    assert exc_info.value.status_code == 403
    create_vk_mock.assert_not_called()


@pytest.mark.asyncio
async def test_create_vk_channel_verifies_provider_before_persisting(mocker):
    user_id = uuid4()
    data = VKChannelCreate(name="VK", group_id="123", community_token="token")
    mocker.patch.object(channel_service, "_check_plan_limit")
    verify = mocker.patch.object(channel_service, "_verify_vk_channel")
    mocker.patch.object(channel_service.channel_repo, "get_external", return_value=None)
    create = mocker.patch.object(
        channel_service.channel_repo,
        "create_vk",
        return_value=SimpleNamespace(
            id=uuid4(),
            platform="vk",
            name="VK",
            is_active=True,
            vk_config=None,
            tg_config=None,
        ),
    )
    db = SimpleNamespace(commit=mocker.AsyncMock())

    await channel_service.create_vk_channel(db, user_id, data)

    verify.assert_awaited_once_with(data.group_id, data.community_token)
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_disable_channel_rejects_active_publication(mocker):
    user_id = uuid4()
    channel_id = uuid4()
    channel = SimpleNamespace(id=channel_id, user_id=user_id, is_active=True)
    mocker.patch.object(
        channel_service.channel_repo, "get_by_id_for_update", return_value=channel
    )
    mocker.patch.object(
        channel_service.channel_repo, "has_active_publish_attempt", return_value=True
    )

    with pytest.raises(HTTPException) as exc_info:
        await channel_service.update_channel(
            object(),
            user_id,
            channel_id,
            channel_service.ChannelUpdate(is_active=False),
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_duplicate_vk_channel_is_rejected(mocker):
    user_id = uuid4()
    data = VKChannelCreate(name="VK", group_id="123", community_token="token")
    mocker.patch.object(channel_service, "_check_plan_limit")
    mocker.patch.object(channel_service, "_verify_vk_channel")
    mocker.patch.object(
        channel_service.channel_repo,
        "get_external",
        return_value=SimpleNamespace(is_active=True),
    )
    create = mocker.patch.object(channel_service.channel_repo, "create_vk")

    with pytest.raises(HTTPException) as exc_info:
        await channel_service.create_vk_channel(object(), user_id, data)

    assert exc_info.value.status_code == 409
    create.assert_not_called()
