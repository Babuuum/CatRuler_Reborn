import pytest

from app.bot import api_client
from app.bot.keyboards.channels import channels_keyboard
from app.bot.keyboards.generate import generation_channels_keyboard


def test_channels_keyboard_has_pagination_and_add_button():
    keyboard = channels_keyboard(page=1, has_previous=True, has_next=True)
    callbacks = [
        button.callback_data for row in keyboard.inline_keyboard for button in row
    ]

    assert "channels:add" in callbacks
    assert "channels:page:0" in callbacks
    assert "channels:page:2" in callbacks
    assert "channels:menu" in callbacks


def test_generation_keyboard_excludes_disabled_channels():
    keyboard = generation_channels_keyboard(
        [
            {"id": "1", "name": "active", "platform": "vk", "is_active": True},
            {"id": "2", "name": "off", "platform": "vk", "is_active": False},
        ]
    )
    callbacks = [
        button.callback_data for row in keyboard.inline_keyboard for button in row
    ]

    assert "generate:channel:1" in callbacks
    assert "generate:channel:2" not in callbacks


@pytest.mark.asyncio
async def test_create_post_client_passes_asset_and_idempotency(mocker):
    request = mocker.patch.object(
        api_client,
        "_authorized_request",
        new=mocker.AsyncMock(return_value={"id": "post-1"}),
    )
    payload = {
        "channel_id": "channel-1",
        "asset_id": "asset-1",
        "idempotency_key": "request-1",
    }

    result = await api_client.create_post("token", payload)

    assert result == {"id": "post-1"}
    request.assert_awaited_once_with("POST", "/posts", token="token", json=payload)
