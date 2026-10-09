from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.core.db.models.models import Channel, PostQueue, PostStatusEnum
from app.schemas.post import PostCreate

_BASE_OPTIONS = (
    selectinload(PostQueue.channel).selectinload(Channel.vk_config),
    selectinload(PostQueue.channel).selectinload(Channel.tg_config),
)


async def get_all_by_user(
    db: AsyncSession, user_id: UUID, status: PostStatusEnum | None = None
) -> list[PostQueue]:
    stmt = (
        select(PostQueue)
        .join(Channel, PostQueue.channel_id == Channel.id)
        .where(Channel.user_id == user_id)
        .options(*_BASE_OPTIONS)
        .order_by(PostQueue.scheduled_at)
    )
    if status is not None:
        stmt = stmt.where(PostQueue.status == status)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_today_by_user(db: AsyncSession, user_id: UUID) -> int:
    day_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )
    day_end = day_start + timedelta(days=1)

    stmt = (
        select(func.count(PostQueue.id))
        .join(Channel, PostQueue.channel_id == Channel.id)
        .where(
            Channel.user_id == user_id,
            PostQueue.created_at >= day_start,
            PostQueue.created_at < day_end,
        )
    )
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_by_id(db: AsyncSession, post_id: UUID) -> PostQueue | None:
    stmt = select(PostQueue).where(PostQueue.id == post_id).options(*_BASE_OPTIONS)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_idempotency_key(
    db: AsyncSession, channel_id: UUID, idempotency_key: str
) -> PostQueue | None:
    result = await db.execute(
        select(PostQueue)
        .where(
            PostQueue.channel_id == channel_id,
            PostQueue.idempotency_key == idempotency_key,
        )
        .options(*_BASE_OPTIONS)
    )
    return result.scalar_one_or_none()


async def get_due_pending(
    db: AsyncSession, scheduled_before: datetime
) -> list[PostQueue]:
    stmt = (
        select(PostQueue)
        .join(Channel, PostQueue.channel_id == Channel.id)
        .where(
            PostQueue.status == PostStatusEnum.pending,
            PostQueue.scheduled_at <= scheduled_before,
            Channel.is_active.is_(True),
        )
        .options(*_BASE_OPTIONS)
        .order_by(PostQueue.scheduled_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create(
    db: AsyncSession,
    channel_id: UUID,
    data: PostCreate,
    generated_image_key: str | None = None,
) -> PostQueue:
    post = PostQueue(
        channel_id=channel_id,
        idempotency_key=data.idempotency_key,
        scheduled_at=data.scheduled_at,
        content_type=data.content_type,
        text_prompt=data.text_prompt,
        image_prompt=data.image_prompt,
        generated_text=data.generated_text,
        generated_asset_id=data.asset_id,
        generated_image_key=generated_image_key,
    )
    db.add(post)
    await db.flush()

    created = await get_by_id(db, post.id)
    if created is None:
        raise ValueError("Post not found")
    return created


async def update(db: AsyncSession, post_id: UUID, data: dict) -> PostQueue:
    post = await get_by_id(db, post_id)
    if post is None:
        raise ValueError("Post not found")

    for key, value in data.items():
        setattr(post, key, value)

    await db.commit()
    await db.refresh(post)

    updated = await get_by_id(db, post_id)
    if updated is None:
        raise ValueError("Post not found")
    return updated


async def delete(db: AsyncSession, post_id: UUID) -> None:
    post = await get_by_id(db, post_id)
    if post is None:
        raise ValueError("Post not found")

    await db.delete(post)
    await db.commit()


async def retry(db: AsyncSession, post_id: UUID) -> PostQueue:
    post = await get_by_id(db, post_id)
    if post is None:
        raise ValueError("Post not found")

    post.status = PostStatusEnum.pending
    post.error_message = None
    await db.commit()
    await db.refresh(post)

    updated = await get_by_id(db, post_id)
    if updated is None:
        raise ValueError("Post not found")
    return updated


def get_by_id_sync(db: Session, post_id: UUID) -> PostQueue | None:
    stmt = select(PostQueue).where(PostQueue.id == post_id).options(*_BASE_OPTIONS)
    return db.execute(stmt).scalar_one_or_none()


def get_due_pending_sync(db: Session, scheduled_before: datetime) -> list[PostQueue]:
    stmt = (
        select(PostQueue)
        .join(Channel, PostQueue.channel_id == Channel.id)
        .where(
            PostQueue.status == PostStatusEnum.pending,
            PostQueue.scheduled_at <= scheduled_before,
            Channel.is_active.is_(True),
        )
        .options(*_BASE_OPTIONS)
        .order_by(PostQueue.scheduled_at)
    )
    return list(db.execute(stmt).scalars().all())


def update_status_sync(
    db: Session,
    post_id: UUID,
    status: PostStatusEnum,
    error_message: str | None = None,
) -> PostQueue:
    post = get_by_id_sync(db, post_id)
    if post is None:
        raise ValueError("Post not found")

    post.status = status
    post.error_message = error_message
    db.commit()
    db.refresh(post)
    return post


def claim_pending_for_publish_sync(db: Session, post_id: UUID) -> PostQueue | None:
    result = db.execute(
        sa_update(PostQueue)
        .where(
            PostQueue.id == post_id,
            PostQueue.status == PostStatusEnum.pending,
        )
        .values(
            status=PostStatusEnum.in_progress,
            error_message=None,
        )
    )
    if result.rowcount == 0:
        db.rollback()
        return None

    db.commit()
    return get_by_id_sync(db, post_id)


async def claim_for_publish(
    db: AsyncSession,
    post_id: UUID,
    owner: str,
    now: datetime,
    lease_until: datetime,
) -> PostQueue | None:
    attempt_id = uuid4()
    result = await db.execute(
        sa_update(PostQueue)
        .where(
            PostQueue.id == post_id,
            PostQueue.status == PostStatusEnum.pending,
            PostQueue.channel.has(Channel.is_active.is_(True)),
        )
        .values(
            status=PostStatusEnum.in_progress,
            publish_attempt_id=attempt_id,
            publish_owner=owner,
            publish_started_at=now,
            publish_lease_expires_at=lease_until,
            error_message=None,
        )
        .returning(PostQueue.id)
    )
    if result.scalar_one_or_none() is None:
        return None
    await db.commit()
    return await get_by_id(db, post_id)


async def finalize_publish(
    db: AsyncSession,
    post_id: UUID,
    owner: str,
    attempt_id: UUID,
    status: PostStatusEnum,
    *,
    error_message: str | None = None,
    external_post_id: str | None = None,
    external_post_url: str | None = None,
) -> bool:
    result = await db.execute(
        sa_update(PostQueue)
        .where(
            PostQueue.id == post_id,
            PostQueue.status == PostStatusEnum.in_progress,
            PostQueue.publish_owner == owner,
            PostQueue.publish_attempt_id == attempt_id,
        )
        .values(
            status=status,
            error_message=error_message,
            external_post_id=external_post_id,
            external_post_url=external_post_url,
            publish_lease_expires_at=None,
        )
    )
    await db.commit()
    return result.rowcount == 1


async def recover_expired_attempt(
    db: AsyncSession, post_id: UUID, now: datetime
) -> bool:
    result = await db.execute(
        sa_update(PostQueue)
        .where(
            PostQueue.id == post_id,
            PostQueue.status == PostStatusEnum.in_progress,
            PostQueue.publish_lease_expires_at.is_not(None),
            PostQueue.publish_lease_expires_at < now,
        )
        .values(
            status=PostStatusEnum.unknown,
            error_message="Publication worker lease expired; provider outcome unknown",
            publish_lease_expires_at=None,
        )
    )
    await db.commit()
    return result.rowcount == 1


async def fail_pending(db: AsyncSession, post_id: UUID, error_message: str) -> bool:
    result = await db.execute(
        sa_update(PostQueue)
        .where(PostQueue.id == post_id, PostQueue.status == PostStatusEnum.pending)
        .values(status=PostStatusEnum.failed, error_message=error_message)
    )
    await db.commit()
    return result.rowcount == 1


async def mark_unknown(db: AsyncSession, post_id: UUID, error_message: str) -> bool:
    result = await db.execute(
        sa_update(PostQueue)
        .where(PostQueue.id == post_id, PostQueue.status == PostStatusEnum.in_progress)
        .values(
            status=PostStatusEnum.unknown,
            error_message=error_message,
            publish_lease_expires_at=None,
        )
    )
    await db.commit()
    return result.rowcount == 1
