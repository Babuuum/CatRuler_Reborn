from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.db.models.models import PlatformEnum


class ChannelResponse(BaseModel):
    id: UUID
    platform: PlatformEnum
    name: str
    is_active: bool
    created_at: datetime
    vk_group_id: str | None = None
    tg_chat_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class VKChannelCreate(BaseModel):
    name: str
    group_id: str
    community_token: str


class TGChannelCreate(BaseModel):
    name: str
    chat_id: str


class ChannelUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
