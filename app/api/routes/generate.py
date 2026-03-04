from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.db import get_db
from app.core.db.models.models import User
from app.schemas.generate import (
    GenerateImageRequest,
    GenerateImageResponse,
    GenerateTextImageRequest,
    GenerateTextImageResponse,
    GenerateTextRequest,
    GenerateTextResponse,
)
from app.services import generate_service

router = APIRouter(tags=["generate"])


@router.post("/text", response_model=GenerateTextResponse)
async def generate_text(
    data: GenerateTextRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateTextResponse:
    return await generate_service.generate_text(
        db=db,
        user_id=current_user.id,
        prompt=data.prompt,
        channel_id=data.channel_id,
    )


@router.post("/image", response_model=GenerateImageResponse)
async def generate_image(
    data: GenerateImageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateImageResponse:
    return await generate_service.generate_image(
        db=db,
        user_id=current_user.id,
        prompt=data.prompt,
        channel_id=data.channel_id,
    )


@router.post("/text-image", response_model=GenerateTextImageResponse)
async def generate_text_image(
    data: GenerateTextImageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateTextImageResponse:
    return await generate_service.generate_text_image(
        db=db,
        user_id=current_user.id,
        text_prompt=data.text_prompt,
        image_prompt=data.image_prompt,
        channel_id=data.channel_id,
    )
