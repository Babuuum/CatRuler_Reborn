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
        "get_by_id",
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
        "get_by_id",
        return_value=owned_channel,
    )
    delete_mock = mocker.patch.object(channel_service.channel_repo, "delete")

    await channel_service.delete_channel(db, user_id, channel_id)

    delete_mock.assert_awaited_once_with(db, channel_id)


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
