import importlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from celery.exceptions import MaxRetriesExceededError

publish_task = importlib.import_module("app.tasks.publish_post")


def _task_self(mocker):
    return SimpleNamespace(
        request=SimpleNamespace(id="task-1"),
        retry=mocker.Mock(side_effect=AssertionError("retry not expected")),
    )


def test_publish_task_passes_only_ids_to_async_service(mocker):
    expected = {"post_id": "post", "status": "sent"}
    post_id = str(uuid4())
    run_mock = mocker.patch.object(
        publish_task,
        "_with_session",
        new=mocker.AsyncMock(return_value=expected),
    )

    result = publish_task.publish_post.run.__func__(_task_self(mocker), post_id)

    assert result == expected
    run_mock.assert_awaited_once()


def test_publish_task_retries_database_failure_and_passes_exception(mocker):
    task = _task_self(mocker)
    retry_error = RuntimeError("retry")
    task.retry = mocker.Mock(side_effect=retry_error)
    mocker.patch.object(
        publish_task,
        "_with_session",
        new=mocker.AsyncMock(side_effect=ValueError("database unavailable")),
    )

    with pytest.raises(RuntimeError, match="retry"):
        publish_task.publish_post.run.__func__(task, str(uuid4()))

    assert task.retry.call_args.kwargs["exc"].args == ("database unavailable",)


def test_publish_task_does_not_retry_after_retry_exhaustion(mocker):
    task = _task_self(mocker)
    task.retry = mocker.Mock(side_effect=MaxRetriesExceededError())
    mark_mock = mocker.patch.object(
        publish_task, "_mark_status", new=mocker.AsyncMock()
    )
    mocker.patch.object(
        publish_task,
        "_with_session",
        new=mocker.AsyncMock(side_effect=ValueError("database unavailable")),
    )

    with pytest.raises(MaxRetriesExceededError):
        publish_task.publish_post.run.__func__(task, str(uuid4()))

    mark_mock.assert_awaited_once()
