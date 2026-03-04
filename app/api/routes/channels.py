from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.db import get_db
from app.core.db.models.models import User
from app.schemas.channel import (
    ChannelResponse,
    ChannelUpdate,
    TGChannelCreate,
    VKChannelCreate,
)
from app.services import channel_service

router = APIRouter(tags=["channels"])


@router.get("", response_model=list[ChannelResponse])
async def get_channels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChannelResponse]:
    return await channel_service.get_channels(db, current_user.id)


@router.post("/vk", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_vk_channel(
    data: VKChannelCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    return await channel_service.create_vk_channel(db, current_user.id, data)


@router.post("/tg", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_tg_channel(
    data: TGChannelCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    return await channel_service.create_tg_channel(db, current_user.id, data)


@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: UUID,
    data: ChannelUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChannelResponse:
    return await channel_service.update_channel(db, current_user.id, channel_id, data)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await channel_service.delete_channel(db, current_user.id, channel_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
