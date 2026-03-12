from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
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
    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
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


async def create(db: AsyncSession, channel_id: UUID, data: PostCreate) -> PostQueue:
    post = PostQueue(
        channel_id=channel_id,
        scheduled_at=data.scheduled_at,
        content_type=data.content_type,
        text_prompt=data.text_prompt,
        image_prompt=data.image_prompt,
        generated_text=data.generated_text,
    )
    db.add(post)
    await db.commit()

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
