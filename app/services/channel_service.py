from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import PlatformEnum
from app.core.limits import get_channel_limit
from app.core.logger import get_logger
from app.core.settings import get_settings
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
    user = await user_repo.get_by_id_for_update(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    current_count = await channel_repo.count_by_user(db, user_id, active_only=True)
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
    group_id = _normalize_vk_group_id(data.group_id)
    await _check_plan_limit(db, user_id)
    await _verify_vk_channel(group_id, data.community_token)
    existing = await channel_repo.get_external(db, user_id, PlatformEnum.vk, group_id)
    if existing is not None:
        if existing.is_active:
            raise HTTPException(
                status_code=409, detail="This VK community is already connected"
            )
        await channel_repo.update_vk_token(db, existing.id, data.community_token)
        channel = await channel_repo.update(db, existing.id, {"is_active": True})
        return _to_channel_response(channel)
    channel = await channel_repo.create_vk(
        db,
        user_id=user_id,
        name=data.name,
        group_id=group_id,
        community_token=data.community_token,
    )
    await db.commit()
    logger.info("channel_created", user_id=str(user_id), platform="vk")
    return _to_channel_response(channel)


async def create_tg_channel(
    db: AsyncSession, user_id: UUID, data: TGChannelCreate
) -> ChannelResponse:
    await _check_plan_limit(db, user_id)
    await _verify_tg_channel(data.chat_id)
    existing = await channel_repo.get_external(
        db, user_id, PlatformEnum.telegram, data.chat_id
    )
    if existing is not None:
        if existing.is_active:
            raise HTTPException(
                status_code=409, detail="This Telegram channel is already connected"
            )
        channel = await channel_repo.update(db, existing.id, {"is_active": True})
        return _to_channel_response(channel)
    channel = await channel_repo.create_tg(
        db,
        user_id=user_id,
        name=data.name,
        chat_id=data.chat_id,
    )
    await db.commit()
    logger.info("channel_created", user_id=str(user_id), platform="telegram")
    return _to_channel_response(channel)


async def update_channel(
    db: AsyncSession,
    user_id: UUID,
    channel_id: UUID,
    data: ChannelUpdate,
) -> ChannelResponse:
    channel = await channel_repo.get_by_id_for_update(db, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    payload = data.model_dump(exclude_unset=True)
    if payload.get("is_active") is False and channel.is_active:
        if await channel_repo.has_active_publish_attempt(db, channel_id):
            raise HTTPException(
                status_code=409,
                detail="Channel cannot be disabled while a publication is active",
            )
    updated = await channel_repo.update(db, channel_id, payload)
    return _to_channel_response(updated)


async def delete_channel(db: AsyncSession, user_id: UUID, channel_id: UUID) -> None:
    channel = await channel_repo.get_by_id_for_update(db, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if await channel_repo.has_active_publish_attempt(db, channel_id):
        raise HTTPException(
            status_code=409,
            detail="Channel cannot be disabled while a publication is active",
        )
    await channel_repo.update(db, channel_id, {"is_active": False})
    logger.info("channel_disabled", channel_id=str(channel_id))


async def _verify_vk_channel(group_id: str, community_token: str) -> None:
    normalized = _normalize_vk_group_id(group_id)
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                "https://api.vk.com/method/groups.getById",
                params={
                    "group_id": normalized,
                    "access_token": community_token,
                    "v": "5.199",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="VK verification unavailable"
        ) from exc
    groups = payload.get("response", {}).get("groups", [])
    if payload.get("error") or not groups:
        raise HTTPException(
            status_code=422, detail="VK token cannot access this community"
        )
    requested_id = normalized.lstrip("-")
    if requested_id.isdigit() and str(groups[0].get("id")) != requested_id:
        raise HTTPException(
            status_code=422, detail="VK token cannot access this community"
        )


def _normalize_vk_group_id(group_id: str) -> str:
    normalized = group_id.strip().removeprefix("https://vk.com/").strip("/")
    for prefix in ("club", "public", "group"):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :]
    return normalized


async def _verify_tg_channel(chat_id: str) -> None:
    token = get_settings().TELEGRAM_BOT_TOKEN
    if not token:
        raise HTTPException(status_code=503, detail="Telegram verification unavailable")
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            me = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            me.raise_for_status()
            bot_id = me.json().get("result", {}).get("id")
            if not bot_id:
                raise HTTPException(
                    status_code=503, detail="Telegram verification unavailable"
                )
            member = await client.get(
                f"https://api.telegram.org/bot{token}/getChatMember",
                params={"chat_id": chat_id, "user_id": bot_id},
            )
            member.raise_for_status()
            payload = member.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Telegram verification unavailable"
        ) from exc
    status = payload.get("result", {}).get("status")
    if status not in {"administrator", "creator"}:
        raise HTTPException(
            status_code=422, detail="Telegram bot lacks channel admin rights"
        )
