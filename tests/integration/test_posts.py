from datetime import UTC, datetime, timedelta

import pytest

from app.core.db.models.models import (
    Channel,
    ContentTypeEnum,
    PlanEnum,
    PlatformEnum,
    PostQueue,
    PostStatusEnum,
    User,
)
from app.core.jwt import create_access_token


async def _create_user(db_session, *, telegram_id: int) -> User:
    user = User(
        telegram_id=telegram_id,
        plan=PlanEnum.free,
        extended_free=False,
        api_password_hash=None,
        created_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_channel(db_session, *, user_id, name: str = "channel") -> Channel:
    channel = Channel(
        user_id=user_id,
        platform=PlatformEnum.telegram,
        name=name,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return channel


async def _create_post(
    db_session,
    *,
    channel_id,
    status: PostStatusEnum,
) -> PostQueue:
    post = PostQueue(
        channel_id=channel_id,
        scheduled_at=datetime.now(UTC) + timedelta(hours=1),
        status=status,
        content_type=ContentTypeEnum.text,
        text_prompt="text",
        image_prompt=None,
        generated_text=None,
        generated_image_key=None,
        error_message=None,
        created_at=datetime.now(UTC),
    )
    db_session.add(post)
    await db_session.commit()
    await db_session.refresh(post)
    return post


@pytest.mark.asyncio
async def test_create_post_returns_401_without_token(client):
    response = await client.post("/posts", json={})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_post_returns_422_if_text_prompt_missing_for_text(
    client, db_session
):
    user = await _create_user(db_session, telegram_id=3001)
    channel = await _create_channel(db_session, user_id=user.id)
    token = create_access_token(str(user.id))

    response = await client.post(
        "/posts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "channel_id": str(channel.id),
            "scheduled_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "content_type": "text",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_post_returns_403_if_channel_belongs_to_different_user(
    client, db_session
):
    owner = await _create_user(db_session, telegram_id=3002)
    requester = await _create_user(db_session, telegram_id=3003)
    channel = await _create_channel(db_session, user_id=owner.id)
    token = create_access_token(str(requester.id))

    response = await client.post(
        "/posts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "channel_id": str(channel.id),
            "scheduled_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "content_type": "text",
            "text_prompt": "hello",
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_post_returns_409_if_status_sent(client, db_session):
    user = await _create_user(db_session, telegram_id=4001)
    channel = await _create_channel(db_session, user_id=user.id)
    post = await _create_post(
        db_session, channel_id=channel.id, status=PostStatusEnum.sent
    )
    token = create_access_token(str(user.id))

    response = await client.delete(
        f"/posts/{post.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_post_returns_204_on_success(client, db_session):
    user = await _create_user(db_session, telegram_id=4002)
    channel = await _create_channel(db_session, user_id=user.id)
    post = await _create_post(
        db_session,
        channel_id=channel.id,
        status=PostStatusEnum.pending,
    )
    token = create_access_token(str(user.id))

    response = await client.delete(
        f"/posts/{post.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204
