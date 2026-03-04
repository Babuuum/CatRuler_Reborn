from uuid import UUID

from pydantic import BaseModel


class GenerateTextRequest(BaseModel):
    prompt: str
    channel_id: UUID | None = None


class GenerateImageRequest(BaseModel):
    prompt: str
    channel_id: UUID | None = None


class GenerateTextResponse(BaseModel):
    text: str
    provider_used: str


class GenerateImageResponse(BaseModel):
    image_key: str
    provider_used: str


class GenerateTextImageRequest(BaseModel):
    text_prompt: str
    image_prompt: str
    channel_id: UUID | None = None


class GenerateTextImageResponse(BaseModel):
    text: str
    image_key: str
    provider_used_text: str
    provider_used_image: str
