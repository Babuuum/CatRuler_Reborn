from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import generate_service


@pytest.mark.asyncio
async def test_generate_text_uses_user_model_keys(mocker):
    db = object()
    user_id = uuid4()
    fake_generator = mocker.AsyncMock()
    fake_generator.generate_text.return_value = ("hello", "hugging_face")

    generator_cls = mocker.patch.object(
        generate_service,
        "PostGenerator",
        return_value=fake_generator,
    )
    mocker.patch.object(generate_service, "_ensure_channel_access", mocker.AsyncMock())
    mocker.patch.object(generate_service, "_check_generation_limit", mocker.AsyncMock())
    mocker.patch.object(
        generate_service.user_repo,
        "get_by_id",
        return_value=SimpleNamespace(
            text_model_key="hf_qwen",
            image_model_key="hf_sd_spaces",
        ),
    )
    mocker.patch.object(generate_service.usage_log_repo, "create", mocker.AsyncMock())

    result = await generate_service.generate_text(db, user_id, "prompt")

    generator_cls.assert_called_once_with(
        generate_service.get_settings(),
        text_model="hf_qwen",
        image_model="hf_sd_spaces",
    )
    assert result.text == "hello"
    assert result.provider_used == "hugging_face"


@pytest.mark.asyncio
async def test_generate_text_falls_back_for_invalid_model_keys(mocker):
    db = object()
    user_id = uuid4()
    fake_generator = mocker.AsyncMock()
    fake_generator.generate_text.return_value = ("hello", "open_router")

    generator_cls = mocker.patch.object(
        generate_service,
        "PostGenerator",
        return_value=fake_generator,
    )
    warning_mock = mocker.patch.object(generate_service.logger, "warning")
    mocker.patch.object(generate_service, "_ensure_channel_access", mocker.AsyncMock())
    mocker.patch.object(generate_service, "_check_generation_limit", mocker.AsyncMock())
    mocker.patch.object(
        generate_service.user_repo,
        "get_by_id",
        return_value=SimpleNamespace(
            text_model_key="broken-text-key",
            image_model_key="broken-image-key",
        ),
    )
    mocker.patch.object(generate_service.usage_log_repo, "create", mocker.AsyncMock())

    result = await generate_service.generate_text(db, user_id, "prompt")

    generator_cls.assert_called_once_with(
        generate_service.get_settings(),
        text_model="or_gemini",
        image_model="pollen_flux",
    )
    assert warning_mock.call_count == 2
    assert result.text == "hello"
