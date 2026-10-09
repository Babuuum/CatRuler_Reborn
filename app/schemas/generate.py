from uuid import UUID

from pydantic import BaseModel


class GenerateTextRequest(BaseModel):
    prompt: str
    channel_id: UUID


class GenerateImageRequest(BaseModel):
    prompt: str
    channel_id: UUID


class GenerateTextResponse(BaseModel):
    operation_id: UUID
    text: str
    provider_used: str


class GenerateImageResponse(BaseModel):
    operation_id: UUID
    asset_id: UUID
    provider_used: str


class GenerateTextImageRequest(BaseModel):
    text_prompt: str
    image_prompt: str
    channel_id: UUID


class GenerateTextImageResponse(BaseModel):
    operation_id: UUID
    text: str
    asset_id: UUID
    provider_used_text: str
    provider_used_image: str
