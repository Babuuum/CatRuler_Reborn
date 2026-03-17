import importlib
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from celery.exceptions import MaxRetriesExceededError

from app.core.db.models.models import PlatformEnum, PostStatusEnum
from app.core.services.posters.poster import Platform, PublishResult

publish_post_task = importlib.import_module("app.tasks.publish_post")


class _SessionContext:
    def __init__(self, db):
        self._db = db

    def __enter__(self):
        return self._db

    def __exit__(self, exc_type, exc, tb):
        return None


def _run_task(task_self, post_id):
    return publish_post_task.publish_post.run.__func__(task_self, str(post_id))


def _make_post(
    *,
    status: PostStatusEnum = PostStatusEnum.pending,
    platform: PlatformEnum = PlatformEnum.telegram,
    image_key: str | None = None,
):
    channel_id = uuid4()
    channel = SimpleNamespace(platform=platform, tg_config=None, vk_config=None)
    if platform == PlatformEnum.telegram:
        channel.tg_config = SimpleNamespace(chat_id="@channel")
    else:
        channel.vk_config = SimpleNamespace(group_id="42", community_token="vk-token")

    return SimpleNamespace(
        id=uuid4(),
        channel_id=channel_id,
        status=status,
        generated_text="generated text",
        text_prompt="prompt text",
        generated_image_key=image_key,
        channel=channel,
    )


def test_download_image_uses_storage_service(mocker):
    download_mock = mocker.patch.object(
        publish_post_task.storage,
        "download_file",
        mocker.AsyncMock(return_value=b"image-bytes"),
    )

    result = publish_post_task._download_image("images/example.jpg")

    assert result == b"image-bytes"
    download_mock.assert_awaited_once_with("images/example.jpg")


def test_build_platform_uses_vk_property_token():
    post = _make_post(platform=PlatformEnum.vk)

    platform = publish_post_task._build_platform(post)

    assert platform.type == "vk"
    assert platform.channel_id == "42"
    assert platform.token == "vk-token"


def test_provider_error_sanitizes_http_status_without_token():
    adapter = publish_post_task.SocialPublisher(
        [Platform(type="telegram", channel_id="@channel", token="secret-token")]
    )._adapters[0]
    request = httpx.Request(
        "POST",
        "https://api.telegram.org/botsecret-token/sendMessage",
    )
    response = httpx.Response(status_code=401, request=request)
    exc = httpx.HTTPStatusError("token leaked", request=request, response=response)

    result = adapter._provider_error(exc)

    assert result == "provider error: 401"
    assert "secret-token" not in result


def test_provider_error_sanitizes_connection_failure_without_token():
    adapter = publish_post_task.SocialPublisher(
        [Platform(type="vk", channel_id="42", token="secret-token")]
    )._adapters[0]
    request = httpx.Request(
        "POST",
        "https://api.vk.com/method/wall.post?access_token=secret-token",
    )
    exc = httpx.ConnectError("token leaked", request=request)

    result = adapter._provider_error(exc)

    assert result == "provider error: connection failed"
    assert "secret-token" not in result


def test_publish_post_marks_sent_after_success(mocker):
    post = _make_post(image_key="images/example.jpg")
    db = object()
    mocker.patch.object(
        publish_post_task,
        "_get_session_factory",
        return_value=lambda: _SessionContext(db),
    )
    claim_mock = mocker.patch.object(
        publish_post_task.post_repo,
        "claim_pending_for_publish_sync",
        return_value=post,
    )
    update_mock = mocker.patch.object(publish_post_task.post_repo, "update_status_sync")
    mocker.patch.object(
        publish_post_task, "_download_image", return_value=b"image-bytes"
    )
    publish_sync_mock = mocker.patch.object(
        publish_post_task.SocialPublisher,
        "publish_sync",
        return_value=[
            PublishResult(
                platform="telegram",
                channel_id="@channel",
                success=True,
                post_id="1",
            )
        ],
    )
    task_self = SimpleNamespace(
        request=SimpleNamespace(id="task-1"),
        retry=mocker.Mock(side_effect=AssertionError("retry not expected")),
    )

    result = _run_task(task_self, post.id)

    assert result["status"] == PostStatusEnum.sent.value
    claim_mock.assert_called_once()
    publish_sync_mock.assert_called_once_with("generated text", b"image-bytes")
    update_mock.assert_called_once_with(
        db,
        post.id,
        PostStatusEnum.sent,
    )


def test_publish_post_skips_when_already_claimed(mocker):
    current_post = _make_post(status=PostStatusEnum.in_progress)
    mocker.patch.object(
        publish_post_task,
        "_get_session_factory",
        return_value=lambda: _SessionContext(object()),
    )
    mocker.patch.object(
        publish_post_task.post_repo,
        "claim_pending_for_publish_sync",
        return_value=None,
    )
    mocker.patch.object(
        publish_post_task.post_repo,
        "get_by_id_sync",
        return_value=current_post,
    )
    publish_sync_mock = mocker.patch.object(
        publish_post_task.SocialPublisher,
        "publish_sync",
    )
    task_self = SimpleNamespace(
        request=SimpleNamespace(id="task-2"),
        retry=mocker.Mock(side_effect=AssertionError("retry not expected")),
    )

    result = _run_task(task_self, current_post.id)

    assert result["status"] == PostStatusEnum.in_progress.value
    assert result["skipped"] is True
    publish_sync_mock.assert_not_called()


def test_publish_post_sets_failed_on_provider_error(mocker):
    post = _make_post(platform=PlatformEnum.vk)
    db = object()
    mocker.patch.object(
        publish_post_task,
        "_get_session_factory",
        return_value=lambda: _SessionContext(db),
    )
    mocker.patch.object(
        publish_post_task.post_repo,
        "claim_pending_for_publish_sync",
        return_value=post,
    )
    update_mock = mocker.patch.object(publish_post_task.post_repo, "update_status_sync")
    mocker.patch.object(
        publish_post_task.SocialPublisher,
        "publish_sync",
        return_value=[
            PublishResult(
                platform="vk",
                channel_id="42",
                success=False,
                error="provider failed",
            )
        ],
    )
    task_self = SimpleNamespace(
        request=SimpleNamespace(id="task-3"),
        retry=mocker.Mock(side_effect=AssertionError("retry not expected")),
    )

    result = _run_task(task_self, post.id)

    assert result["status"] == PostStatusEnum.failed.value
    update_mock.assert_called_once_with(
        db,
        post.id,
        PostStatusEnum.failed,
        error_message="provider failed",
    )


@pytest.mark.parametrize(
    ("retry_side_effect", "expected_status"),
    [
        (RuntimeError("retry-triggered"), PostStatusEnum.pending),
        (MaxRetriesExceededError(), PostStatusEnum.failed),
    ],
)
def test_publish_post_updates_status_for_retry_paths(
    mocker, retry_side_effect, expected_status
):
    post = _make_post(image_key="images/example.jpg")
    db = object()

    def session_factory():
        return _SessionContext(db)

    mocker.patch.object(
        publish_post_task,
        "_get_session_factory",
        return_value=session_factory,
    )
    claim_mock = mocker.patch.object(
        publish_post_task.post_repo,
        "claim_pending_for_publish_sync",
        return_value=post,
    )
    get_mock = mocker.patch.object(
        publish_post_task.post_repo,
        "get_by_id_sync",
        return_value=SimpleNamespace(id=post.id, status=PostStatusEnum.in_progress),
    )
    update_mock = mocker.patch.object(publish_post_task.post_repo, "update_status_sync")
    mocker.patch.object(
        publish_post_task,
        "_download_image",
        side_effect=RuntimeError("storage failed"),
    )
    task_self = SimpleNamespace(
        request=SimpleNamespace(id="task-4"),
        retry=mocker.Mock(side_effect=retry_side_effect),
    )

    with pytest.raises(type(retry_side_effect)):
        _run_task(task_self, post.id)

    claim_mock.assert_called_once()
    get_mock.assert_called()
    assert update_mock.call_args_list[0].args[2] == PostStatusEnum.pending
    assert update_mock.call_args_list[-1].args[2] == expected_status


def test_publish_post_terminal_failure_sanitizes_error_message(mocker):
    post = _make_post(image_key="images/example.jpg")
    db = object()

    def session_factory():
        return _SessionContext(db)

    mocker.patch.object(
        publish_post_task,
        "_get_session_factory",
        return_value=session_factory,
    )
    mocker.patch.object(
        publish_post_task.post_repo,
        "claim_pending_for_publish_sync",
        return_value=post,
    )
    mocker.patch.object(
        publish_post_task.post_repo,
        "get_by_id_sync",
        return_value=SimpleNamespace(id=post.id, status=PostStatusEnum.in_progress),
    )
    update_mock = mocker.patch.object(publish_post_task.post_repo, "update_status_sync")
    mocker.patch.object(
        publish_post_task,
        "_download_image",
        side_effect=RuntimeError("secret-token leaked"),
    )
    task_self = SimpleNamespace(
        request=SimpleNamespace(id="task-5"),
        retry=mocker.Mock(side_effect=MaxRetriesExceededError()),
    )

    with pytest.raises(MaxRetriesExceededError):
        _run_task(task_self, post.id)

    assert update_mock.call_args_list[-1].kwargs["error_message"] == (
        "publish failed: RuntimeError"
    )
