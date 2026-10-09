from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db.models.models import (
    Channel,
    PlatformEnum,
    PostQueue,
    PostStatusEnum,
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


async def count_by_user(
    db: AsyncSession, user_id: UUID, *, active_only: bool = False
) -> int:
    stmt = select(func.count(Channel.id)).where(Channel.user_id == user_id)
    if active_only:
        stmt = stmt.where(Channel.is_active.is_(True))
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def get_external(
    db: AsyncSession,
    user_id: UUID,
    platform: PlatformEnum,
    external_id: str,
) -> Channel | None:
    config_model = VKChannelConfig if platform == PlatformEnum.vk else TGChannelConfig
    external_column = (
        config_model.group_id if platform == PlatformEnum.vk else config_model.chat_id
    )
    result = await db.execute(
        select(Channel)
        .join(config_model, Channel.id == config_model.channel_id)
        .where(
            Channel.user_id == user_id,
            Channel.platform == platform,
            external_column == external_id,
        )
        .options(*_BASE_OPTIONS)
    )
    return result.scalar_one_or_none()


async def update_vk_token(
    db: AsyncSession, channel_id: UUID, community_token: str
) -> None:
    result = await db.execute(
        select(VKChannelConfig).where(VKChannelConfig.channel_id == channel_id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise ValueError("VK channel config not found")
    config._community_token = community_token
    await db.flush()


async def get_by_id(db: AsyncSession, channel_id: UUID) -> Channel | None:
    stmt = select(Channel).where(Channel.id == channel_id).options(*_BASE_OPTIONS)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_id_for_update(db: AsyncSession, channel_id: UUID) -> Channel | None:
    result = await db.execute(
        select(Channel)
        .where(Channel.id == channel_id)
        .options(*_BASE_OPTIONS)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def has_active_publish_attempt(db: AsyncSession, channel_id: UUID) -> bool:
    result = await db.execute(
        select(
            exists().where(
                PostQueue.channel_id == channel_id,
                PostQueue.status == PostStatusEnum.in_progress,
            )
        )
    )
    return bool(result.scalar())


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
    await db.flush()

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
    await db.flush()

    created = await get_by_id(db, channel.id)
    if created is None:
        raise ValueError("Channel not found")
    return created


async def update(db: AsyncSession, channel_id: UUID, data: dict) -> Channel:
    channel = await get_by_id_for_update(db, channel_id)
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
    raise RuntimeError("Physical channel deletion is disabled; deactivate it instead")
