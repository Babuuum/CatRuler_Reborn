from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.db.models.models import ContentTypeEnum, PostStatusEnum
from app.schemas.post import PostCreate
from app.services import post_service


def _make_post(status: PostStatusEnum, owner_id):
    return SimpleNamespace(
        id=uuid4(),
        channel_id=uuid4(),
        scheduled_at=datetime.now(UTC),
        status=status,
        content_type=ContentTypeEnum.text,
        text_prompt="text",
        image_prompt=None,
        generated_text=None,
        generated_image_key=None,
        error_message=None,
        created_at=datetime.now(UTC),
        channel=SimpleNamespace(user_id=owner_id),
    )


@pytest.mark.asyncio
async def test_delete_post_returns_409_if_sent(mocker):
    user_id = uuid4()
    post = _make_post(PostStatusEnum.sent, user_id)
    mocker.patch.object(post_service.post_repo, "get_by_id", return_value=post)

    with pytest.raises(HTTPException) as exc_info:
        await post_service.delete_post(object(), user_id, post.id)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_post_returns_409_if_failed(mocker):
    user_id = uuid4()
    post = _make_post(PostStatusEnum.failed, user_id)
    mocker.patch.object(post_service.post_repo, "get_by_id", return_value=post)

    with pytest.raises(HTTPException) as exc_info:
        await post_service.delete_post(object(), user_id, post.id)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_post_succeeds_if_pending(mocker):
    db = object()
    user_id = uuid4()
    post = _make_post(PostStatusEnum.pending, user_id)
    delete_mock = mocker.patch.object(post_service.post_repo, "delete")
    mocker.patch.object(post_service.post_repo, "get_by_id", return_value=post)

    await post_service.delete_post(db, user_id, post.id)

    delete_mock.assert_awaited_once_with(db, post.id)


@pytest.mark.asyncio
async def test_delete_post_returns_403_for_other_user(mocker):
    user_id = uuid4()
    post = _make_post(PostStatusEnum.pending, uuid4())
    mocker.patch.object(post_service.post_repo, "get_by_id", return_value=post)

    with pytest.raises(HTTPException) as exc_info:
        await post_service.delete_post(object(), user_id, post.id)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_retry_post_returns_409_if_pending(mocker):
    user_id = uuid4()
    post = _make_post(PostStatusEnum.pending, user_id)
    mocker.patch.object(post_service.post_repo, "get_by_id", return_value=post)

    with pytest.raises(HTTPException) as exc_info:
        await post_service.retry_post(object(), user_id, post.id)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_retry_post_returns_409_if_sent(mocker):
    user_id = uuid4()
    post = _make_post(PostStatusEnum.sent, user_id)
    mocker.patch.object(post_service.post_repo, "get_by_id", return_value=post)

    with pytest.raises(HTTPException) as exc_info:
        await post_service.retry_post(object(), user_id, post.id)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_retry_post_succeeds_if_failed(mocker):
    db = object()
    user_id = uuid4()
    post = _make_post(PostStatusEnum.failed, user_id)
    retried = _make_post(PostStatusEnum.pending, user_id)

    mocker.patch.object(post_service.post_repo, "get_by_id", return_value=post)
    retry_mock = mocker.patch.object(
        post_service.post_repo, "retry", return_value=retried
    )

    result = await post_service.retry_post(db, user_id, post.id)

    assert result.status == PostStatusEnum.pending
    retry_mock.assert_awaited_once_with(db, post.id)


@pytest.mark.asyncio
async def test_create_post_returns_403_for_foreign_channel(mocker):
    user_id = uuid4()
    data = PostCreate(
        channel_id=uuid4(),
        scheduled_at=datetime.now(UTC),
        content_type=ContentTypeEnum.text,
        text_prompt="text",
    )

    mocker.patch.object(
        post_service.channel_repo,
        "get_by_id",
        return_value=SimpleNamespace(user_id=uuid4()),
    )

    with pytest.raises(HTTPException) as exc_info:
        await post_service.create_post(object(), user_id, data)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_create_post_returns_403_if_daily_limit_exceeded(mocker):
    user_id = uuid4()
    channel_id = uuid4()
    data = PostCreate(
        channel_id=channel_id,
        scheduled_at=datetime.now(UTC),
        content_type=ContentTypeEnum.text,
        text_prompt="text",
    )

    mocker.patch.object(
        post_service.channel_repo,
        "get_by_id",
        return_value=SimpleNamespace(id=channel_id, user_id=user_id),
    )
    mocker.patch.object(
        post_service,
        "_check_daily_post_limit",
        side_effect=HTTPException(status_code=403, detail="Daily post limit reached"),
    )
    create_mock = mocker.patch.object(post_service.post_repo, "create")

    with pytest.raises(HTTPException) as exc_info:
        await post_service.create_post(object(), user_id, data)

    assert exc_info.value.status_code == 403
    create_mock.assert_not_called()
