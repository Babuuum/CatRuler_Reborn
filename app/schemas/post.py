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
    has_image: bool
    error_message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostCreate(BaseModel):
    channel_id: UUID
    scheduled_at: datetime
    content_type: ContentTypeEnum
    text_prompt: str | None = None
    image_prompt: str | None = None
    generated_text: str | None = None

    @model_validator(mode="after")
    def validate_prompts(self) -> "PostCreate":
        if self.content_type == ContentTypeEnum.text and not self.text_prompt:
            raise ValueError("text_prompt required for text content")
        if self.content_type == ContentTypeEnum.image and not self.image_prompt:
            raise ValueError("image_prompt required for image content")
        if self.content_type == ContentTypeEnum.text_image:
            if not self.text_prompt or not self.image_prompt:
                raise ValueError(
                    "both text_prompt and image_prompt required for text_image content"
                )
        return self


class PostUpdate(BaseModel):
    scheduled_at: datetime | None = None
    text_prompt: str | None = None
    image_prompt: str | None = None
    generated_text: str | None = None
