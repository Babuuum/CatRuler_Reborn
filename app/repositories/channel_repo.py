from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db.models.models import (
    Channel,
    PlatformEnum,
    TGChannelConfig,
    VKChannelConfig,
)

_BASE_OPTIONS = (selectinload(Channel.vk_config), selectinload(Channel.tg_config))


async def get_all_by_user(db: AsyncSession, user_id: UUID) -> list[Channel]:
    stmt = (
        select(Channel)
        .where(Channel.user_id == user_id)
        .options(*_BASE_OPTIONS)
        .order_by(Channel.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_by_user(db: AsyncSession, user_id: UUID) -> int:
    stmt = select(func.count(Channel.id)).where(Channel.user_id == user_id)
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_by_id(db: AsyncSession, channel_id: UUID) -> Channel | None:
    stmt = select(Channel).where(Channel.id == channel_id).options(*_BASE_OPTIONS)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_vk(
    db: AsyncSession,
    user_id: UUID,
    name: str,
    group_id: str,
    community_token: str,
) -> Channel:
    channel = Channel(user_id=user_id, platform=PlatformEnum.vk, name=name)
    db.add(channel)
    await db.flush()

    vk_config = VKChannelConfig(
        channel_id=channel.id,
        group_id=group_id,
        _community_token=community_token,
    )
    db.add(vk_config)
    await db.flush()
    await db.commit()

    created = await get_by_id(db, channel.id)
    if created is None:
        raise ValueError("Channel not found")
    return created


async def create_tg(
    db: AsyncSession, user_id: UUID, name: str, chat_id: str
) -> Channel:
    channel = Channel(user_id=user_id, platform=PlatformEnum.telegram, name=name)
    db.add(channel)
    await db.flush()

    db.add(TGChannelConfig(channel_id=channel.id, chat_id=chat_id))
    await db.commit()

    created = await get_by_id(db, channel.id)
    if created is None:
        raise ValueError("Channel not found")
    return created


async def update(db: AsyncSession, channel_id: UUID, data: dict) -> Channel:
    channel = await get_by_id(db, channel_id)
    if channel is None:
        raise ValueError("Channel not found")

    for key, value in data.items():
        setattr(channel, key, value)

    await db.commit()
    await db.refresh(channel)

    updated = await get_by_id(db, channel_id)
    if updated is None:
        raise ValueError("Channel not found")
    return updated


async def delete(db: AsyncSession, channel_id: UUID) -> None:
    channel = await get_by_id(db, channel_id)
    if channel is None:
        raise ValueError("Channel not found")

    await db.delete(channel)
    await db.commit()
