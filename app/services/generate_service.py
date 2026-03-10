from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import ActionEnum
from app.core.limits import get_daily_generation_limit
from app.core.logger import get_logger
from app.core.services import storage
from app.core.services.generation.post_generator import PostGenerator, ProviderError
from app.core.settings import get_settings
from app.repositories import channel_repo, usage_log_repo, user_repo
from app.schemas.generate import (
    GenerateImageResponse,
    GenerateTextImageResponse,
    GenerateTextResponse,
)

logger = get_logger(__name__)


async def _ensure_channel_access(
    db: AsyncSession,
    user_id: UUID,
    channel_id: UUID | None,
) -> None:
    if channel_id is None:
        return

    channel = await channel_repo.get_by_id(db, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")


async def _check_generation_limit(db: AsyncSession, user_id: UUID, needed: int) -> None:
    user = await user_repo.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    limit = get_daily_generation_limit(user.plan, user.extended_free)
    used_text = await usage_log_repo.count_today(db, user_id, ActionEnum.post_generated)
    used_image = await usage_log_repo.count_today(
        db, user_id, ActionEnum.image_generated
    )
    used_total = used_text + used_image

    if used_total + needed > limit:
        raise HTTPException(
            status_code=403,
            detail=f"Daily generation limit reached for your plan ({limit} per day)",
        )


def _ensure_storage_configured() -> None:
    settings = get_settings()
    if (
        not settings.YANDEX_ACCESS_KEY
        or not settings.YANDEX_SECRET_KEY
        or not settings.YANDEX_BUCKET_NAME
    ):
        raise HTTPException(status_code=503, detail="Storage not configured")


async def _upload_generated_image(user_id: UUID, image_bytes: bytes) -> str:
    _ensure_storage_configured()

    key = f"generated/{user_id}/{uuid4()}.jpg"
    try:
        await storage.upload_image(key, image_bytes)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Image upload failed") from exc

    return key


async def generate_text(
    db: AsyncSession,
    user_id: UUID,
    prompt: str,
    channel_id: UUID | None = None,
) -> GenerateTextResponse:
    await _ensure_channel_access(db, user_id, channel_id)
    await _check_generation_limit(db, user_id, needed=1)

    generator = PostGenerator(get_settings())
    try:
        text, provider_used = await generator.generate_text(prompt)
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail="All generation providers failed. Try again later.",
        ) from exc

    await usage_log_repo.create(db, user_id, ActionEnum.post_generated)
    logger.info(
        "text_generated",
        user_id=str(user_id),
        provider=provider_used,
        prompt_length=len(prompt),
    )
    return GenerateTextResponse(text=text, provider_used=provider_used)


async def generate_image(
    db: AsyncSession,
    user_id: UUID,
    prompt: str,
    channel_id: UUID | None = None,
) -> GenerateImageResponse:
    await _ensure_channel_access(db, user_id, channel_id)
    await _check_generation_limit(db, user_id, needed=1)

    generator = PostGenerator(get_settings())
    try:
        image_bytes, provider_used = await generator.generate_image(prompt)
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail="All generation providers failed. Try again later.",
        ) from exc
    image_key = await _upload_generated_image(user_id, image_bytes)

    await usage_log_repo.create(db, user_id, ActionEnum.image_generated)
    logger.info(
        "image_generated",
        user_id=str(user_id),
        provider=provider_used,
        prompt_length=len(prompt),
    )
    return GenerateImageResponse(image_key=image_key, provider_used=provider_used)


async def generate_text_image(
    db: AsyncSession,
    user_id: UUID,
    text_prompt: str,
    image_prompt: str,
    channel_id: UUID | None = None,
) -> GenerateTextImageResponse:
    await _ensure_channel_access(db, user_id, channel_id)
    await _check_generation_limit(db, user_id, needed=2)

    generator = PostGenerator(get_settings())
    try:
        text, provider_used_text = await generator.generate_text(text_prompt)
        image_bytes, provider_used_image = await generator.generate_image(image_prompt)
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail="All generation providers failed. Try again later.",
        ) from exc
    image_key = await _upload_generated_image(user_id, image_bytes)

    await usage_log_repo.create_bulk(
        db,
        user_id,
        [ActionEnum.post_generated, ActionEnum.image_generated],
    )

    logger.info(
        "text_image_generated",
        user_id=str(user_id),
        provider_text=provider_used_text,
        provider_image=provider_used_image,
        text_prompt_length=len(text_prompt),
        image_prompt_length=len(image_prompt),
    )

    return GenerateTextImageResponse(
        text=text,
        image_key=image_key,
        provider_used_text=provider_used_text,
        provider_used_image=provider_used_image,
    )
