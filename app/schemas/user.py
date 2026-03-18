from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.db.models.models import PlanEnum
from app.core.generation_models import (
    is_valid_image_model_key,
    is_valid_text_model_key,
)


class UserResponse(BaseModel):
    id: UUID
    telegram_id: int
    plan: PlanEnum
    extended_free: bool
    has_api_password: bool
    text_model_key: str
    image_model_key: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    text_model_key: str | None = None
    image_model_key: str | None = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("text_model_key", mode="before")
    @classmethod
    def reject_null_text_model_key(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("text_model_key cannot be null")
        return value

    @field_validator("text_model_key")
    @classmethod
    def validate_text_model_key(cls, value: str | None) -> str | None:
        if not is_valid_text_model_key(value):
            raise ValueError("Invalid text_model_key")
        return value

    @field_validator("image_model_key", mode="before")
    @classmethod
    def reject_null_image_model_key(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("image_model_key cannot be null")
        return value

    @field_validator("image_model_key")
    @classmethod
    def validate_image_model_key(cls, value: str | None) -> str | None:
        if not is_valid_image_model_key(value):
            raise ValueError("Invalid image_model_key")
        return value


class UserStats(BaseModel):
    plan: PlanEnum
    channels_count: int
    channels_limit: int
    posts_today: int
    posts_limit: int
    generations_today: int
    generations_limit: int
