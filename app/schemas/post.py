from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.db.models.models import ContentTypeEnum, PostStatusEnum


class PostResponse(BaseModel):
    id: UUID
    channel_id: UUID
    scheduled_at: datetime
    status: PostStatusEnum
    content_type: ContentTypeEnum
    text_prompt: str | None = None
    image_prompt: str | None = None
    generated_text: str | None = None
    asset_id: UUID | None = None
    has_image: bool
    error_message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostCreate(BaseModel):
    channel_id: UUID
    idempotency_key: str | None = None
    scheduled_at: datetime
    content_type: ContentTypeEnum
    text_prompt: str | None = None
    image_prompt: str | None = None
    generated_text: str | None = None
    asset_id: UUID | None = None

    @model_validator(mode="after")
    def validate_prompts(self) -> "PostCreate":
        if self.content_type == ContentTypeEnum.text and not (
            self.text_prompt or self.generated_text
        ):
            raise ValueError("text_prompt or generated_text required for text content")
        if self.content_type == ContentTypeEnum.image and not (
            self.image_prompt or self.asset_id
        ):
            raise ValueError("image_prompt or asset_id required for image content")
        if self.content_type == ContentTypeEnum.text_image:
            if not (self.text_prompt or self.generated_text) or not (
                self.image_prompt or self.asset_id
            ):
                raise ValueError(
                    "text_prompt and image_prompt or asset_id required for text_image content"
                )
        return self


class PostUpdate(BaseModel):
    scheduled_at: datetime | None = None
    text_prompt: str | None = None
    image_prompt: str | None = None
    generated_text: str | None = None
    asset_id: UUID | None = None
