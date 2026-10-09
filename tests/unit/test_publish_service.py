from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.db.models.models import ContentTypeEnum, PostStatusEnum
from app.core.services.posters.poster import PublishResult
from app.services import publish_service


def _post(content_type=ContentTypeEnum.text_image, status=PostStatusEnum.pending):
    channel = SimpleNamespace(
        is_active=True,
        platform="telegram",
        tg_config=SimpleNamespace(chat_id="@channel"),
        vk_config=None,
    )
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        content_type=content_type,
        generated_text="ready text",
        generated_image_key=(
            "generated/image.jpg" if content_type != ContentTypeEnum.text else None
        ),
        channel=channel,
        publish_attempt_id=uuid4(),
        publish_lease_expires_at=datetime.now(UTC).replace(tzinfo=None)
        + timedelta(minutes=5),
    )


@pytest.mark.asyncio
async def test_publish_service_sends_generated_text_and_image(mocker):
    post = _post()
    claimed = _post()
    claimed.publish_attempt_id = uuid4()
    mocker.patch.object(publish_service.post_repo, "get_by_id", return_value=post)
    mocker.patch.object(
        publish_service.post_repo, "claim_for_publish", return_value=claimed
    )
    finalize = mocker.patch.object(
        publish_service.post_repo, "finalize_publish", return_value=True
    )
    mocker.patch.object(
        publish_service.storage,
        "download_file",
        new=mocker.AsyncMock(return_value=b"image"),
    )
    publisher = mocker.Mock()
    publisher.publish = mocker.AsyncMock(
        return_value=[PublishResult("telegram", "@channel", True, post_id="42")]
    )
    factory = mocker.Mock(return_value=publisher)

    result = await publish_service.publish_post(
        object(), post.id, "task", publisher_factory=factory
    )

    assert result["status"] == PostStatusEnum.sent.value
    publisher.publish.assert_awaited_once_with("ready text", b"image")
    assert finalize.call_args.kwargs["external_post_id"] == "42"


@pytest.mark.asyncio
async def test_provider_transport_failure_is_unknown_and_never_retried(mocker):
    post = _post(content_type=ContentTypeEnum.text)
    claimed = _post(content_type=ContentTypeEnum.text)
    mocker.patch.object(publish_service.post_repo, "get_by_id", return_value=post)
    mocker.patch.object(
        publish_service.post_repo, "claim_for_publish", return_value=claimed
    )
    finalize = mocker.patch.object(
        publish_service.post_repo, "finalize_publish", return_value=True
    )
    publisher = mocker.Mock()
    publisher.publish = mocker.AsyncMock(side_effect=TimeoutError())

    result = await publish_service.publish_post(
        object(), post.id, "task", publisher_factory=mocker.Mock(return_value=publisher)
    )

    assert result["status"] == PostStatusEnum.unknown.value
    assert finalize.call_args.args[4] == PostStatusEnum.unknown


@pytest.mark.asyncio
async def test_storage_failure_before_provider_is_retryable_failure(mocker):
    post = _post()
    claimed = _post()
    mocker.patch.object(publish_service.post_repo, "get_by_id", return_value=post)
    mocker.patch.object(
        publish_service.post_repo, "claim_for_publish", return_value=claimed
    )
    finalize = mocker.patch.object(
        publish_service.post_repo, "finalize_publish", return_value=True
    )
    mocker.patch.object(
        publish_service.storage,
        "download_file",
        new=mocker.AsyncMock(side_effect=ConnectionError()),
    )

    result = await publish_service.publish_post(
        object(), post.id, "task", publisher_factory=mocker.Mock()
    )

    assert result["status"] == PostStatusEnum.failed.value
    assert finalize.call_args.args[4] == PostStatusEnum.failed


@pytest.mark.asyncio
async def test_prompt_only_post_fails_without_sending(mocker):
    post = _post(content_type=ContentTypeEnum.text)
    post.generated_text = None
    mocker.patch.object(publish_service.post_repo, "get_by_id", return_value=post)
    claimed = _post(content_type=ContentTypeEnum.text)
    claimed.generated_text = None
    mocker.patch.object(
        publish_service.post_repo, "claim_for_publish", return_value=claimed
    )
    finalize = mocker.patch.object(
        publish_service.post_repo, "finalize_publish", return_value=True
    )
    factory = mocker.Mock()

    result = await publish_service.publish_post(
        object(), post.id, "task", publisher_factory=factory
    )

    assert result["status"] == PostStatusEnum.failed.value
    factory.assert_not_called()
    assert finalize.call_args.args[4] == PostStatusEnum.failed


@pytest.mark.asyncio
async def test_save_failure_after_provider_success_becomes_unknown(mocker):
    post = _post(content_type=ContentTypeEnum.text)
    claimed = _post(content_type=ContentTypeEnum.text)
    mocker.patch.object(publish_service.post_repo, "get_by_id", return_value=post)
    mocker.patch.object(
        publish_service.post_repo, "claim_for_publish", return_value=claimed
    )
    mocker.patch.object(
        publish_service.post_repo,
        "finalize_publish",
        side_effect=RuntimeError("db unavailable"),
    )
    publisher = mocker.Mock()
    publisher.publish = mocker.AsyncMock(
        return_value=[PublishResult("telegram", "@channel", True, post_id="1")]
    )
    db = SimpleNamespace(rollback=mocker.AsyncMock())

    result = await publish_service.publish_post(
        db, post.id, "task", publisher_factory=mocker.Mock(return_value=publisher)
    )

    assert result["status"] == PostStatusEnum.unknown.value
    db.rollback.assert_awaited_once()
