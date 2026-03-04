from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.db.models.models import PlanEnum


class UserResponse(BaseModel):
    id: UUID
    telegram_id: int
    plan: PlanEnum
    extended_free: bool
    has_api_password: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    extended_free: bool | None = None


class UserStats(BaseModel):
    total_posts_sent: int
    posts_today: int
    posts_this_month: int
    channels_count: int
    plan_limit_today: int
    plan_limit_remaining: int
