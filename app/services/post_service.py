from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import PostQueue, PostStatusEnum
from app.core.limits import get_daily_post_limit
from app.core.logger import get_logger
from app.repositories import channel_repo, post_repo, user_repo
from app.schemas.post import PostCreate, PostResponse, PostUpdate

_PENDING_ONLY_DETAIL = "Operation allowed only for pending posts"
logger = get_logger(__name__)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_post_response(post: PostQueue) -> PostResponse:
    return PostResponse(
        id=post.id,
        channel_id=post.channel_id,
        scheduled_at=post.scheduled_at,
        status=post.status,
        content_type=post.content_type,
        text_prompt=post.text_prompt,
        image_prompt=post.image_prompt,
        generated_text=post.generated_text,
        has_image=bool(post.generated_image_key),
        error_message=post.error_message,
        created_at=post.created_at,
    )


async def _get_owned_post(
    db: AsyncSession,
    user_id: UUID,
    post_id: UUID,
) -> PostQueue:
    post = await post_repo.get_by_id(db, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.channel is None or post.channel.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return post


async def _check_daily_post_limit(db: AsyncSession, user_id: UUID) -> None:
    user = await user_repo.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    limit = get_daily_post_limit(user.plan, user.extended_free)

    now = datetime.now(UTC)
    day_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    posts = await post_repo.get_all_by_user(db, user_id)
    today_count = sum(
        1 for post in posts if day_start <= _as_utc(post.created_at) < day_end
    )
    if today_count >= limit:
        logger.warning("daily_post_limit_reached", user_id=str(user_id))
        raise HTTPException(
            status_code=403,
            detail=f"Daily post limit reached for your plan ({limit} per day)",
        )


async def get_posts(
    db: AsyncSession,
    user_id: UUID,
    status: PostStatusEnum | None,
) -> list[PostResponse]:
    posts = await post_repo.get_all_by_user(db, user_id, status)
    return [_to_post_response(post) for post in posts]


async def create_post(
    db: AsyncSession, user_id: UUID, data: PostCreate
) -> PostResponse:
    channel = await channel_repo.get_by_id(db, data.channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    await _check_daily_post_limit(db, user_id)

    post = await post_repo.create(db, data.channel_id, data)
    logger.info("post_created", user_id=str(user_id), channel_id=str(data.channel_id))
    return _to_post_response(post)


async def get_post(db: AsyncSession, user_id: UUID, post_id: UUID) -> PostResponse:
    post = await _get_owned_post(db, user_id, post_id)
    return _to_post_response(post)


async def update_post(
    db: AsyncSession,
    user_id: UUID,
    post_id: UUID,
    data: PostUpdate,
) -> PostResponse:
    post = await _get_owned_post(db, user_id, post_id)
    if post.status != PostStatusEnum.pending:
        raise HTTPException(status_code=409, detail=_PENDING_ONLY_DETAIL)

    payload = data.model_dump(exclude_unset=True)
    updated = await post_repo.update(db, post_id, payload)
    return _to_post_response(updated)


async def delete_post(db: AsyncSession, user_id: UUID, post_id: UUID) -> None:
    post = await _get_owned_post(db, user_id, post_id)
    if post.status != PostStatusEnum.pending:
        raise HTTPException(status_code=409, detail=_PENDING_ONLY_DETAIL)

    await post_repo.delete(db, post_id)


async def retry_post(db: AsyncSession, user_id: UUID, post_id: UUID) -> PostResponse:
    post = await _get_owned_post(db, user_id, post_id)
    if post.status != PostStatusEnum.failed:
        raise HTTPException(
            status_code=409, detail="Retry allowed only for failed posts"
        )

    updated = await post_repo.retry(db, post_id)
    logger.info("post_retry", post_id=str(post_id))
    return _to_post_response(updated)
