from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limits import get_channel_limit
from app.core.logger import get_logger
from app.repositories import channel_repo, user_repo
from app.schemas.channel import (
    ChannelResponse,
    ChannelUpdate,
    TGChannelCreate,
    VKChannelCreate,
)

logger = get_logger(__name__)


def _to_channel_response(channel) -> ChannelResponse:
    return ChannelResponse(
        id=channel.id,
        platform=channel.platform,
        name=channel.name,
        is_active=channel.is_active,
        created_at=getattr(channel, "created_at", datetime.now(UTC)),
        vk_group_id=channel.vk_config.group_id if channel.vk_config else None,
        tg_chat_id=channel.tg_config.chat_id if channel.tg_config else None,
    )


async def get_channels(db: AsyncSession, user_id: UUID) -> list[ChannelResponse]:
    channels = await channel_repo.get_all_by_user(db, user_id)
    return [_to_channel_response(channel) for channel in channels]


async def _check_plan_limit(db: AsyncSession, user_id: UUID) -> None:
    user = await user_repo.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    current_count = len(await channel_repo.get_all_by_user(db, user_id))
    limit = get_channel_limit(user.plan, user.extended_free)
    if current_count >= limit:
        logger.warning(
            "channel_limit_reached",
            user_id=str(user_id),
            plan=str(user.plan),
        )
        raise HTTPException(
            status_code=403, detail="Channel limit reached for your plan"
        )


async def create_vk_channel(
    db: AsyncSession, user_id: UUID, data: VKChannelCreate
) -> ChannelResponse:
    await _check_plan_limit(db, user_id)
    channel = await channel_repo.create_vk(
        db,
        user_id=user_id,
        name=data.name,
        group_id=data.group_id,
        community_token=data.community_token,
    )
    logger.info("channel_created", user_id=str(user_id), platform="vk")
    return _to_channel_response(channel)


async def create_tg_channel(
    db: AsyncSession, user_id: UUID, data: TGChannelCreate
) -> ChannelResponse:
    await _check_plan_limit(db, user_id)
    channel = await channel_repo.create_tg(
        db,
        user_id=user_id,
        name=data.name,
        chat_id=data.chat_id,
    )
    logger.info("channel_created", user_id=str(user_id), platform="telegram")
    return _to_channel_response(channel)


async def update_channel(
    db: AsyncSession,
    user_id: UUID,
    channel_id: UUID,
    data: ChannelUpdate,
) -> ChannelResponse:
    channel = await channel_repo.get_by_id(db, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    payload = data.model_dump(exclude_unset=True)
    updated = await channel_repo.update(db, channel_id, payload)
    return _to_channel_response(updated)


async def delete_channel(db: AsyncSession, user_id: UUID, channel_id: UUID) -> None:
    channel = await channel_repo.get_by_id(db, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    await channel_repo.delete(db, channel_id)
    logger.info("channel_deleted", channel_id=str(channel_id))
