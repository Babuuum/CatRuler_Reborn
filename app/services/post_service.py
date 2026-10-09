from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import ContentTypeEnum, PostQueue, PostStatusEnum
from app.core.limits import get_daily_post_limit
from app.core.logger import get_logger
from app.repositories import asset_repo, channel_repo, post_repo, user_repo
from app.schemas.post import PostCreate, PostResponse, PostUpdate

_PENDING_ONLY_DETAIL = "Operation allowed only for pending posts"
logger = get_logger(__name__)


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
        asset_id=getattr(post, "generated_asset_id", None),
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
    user = await user_repo.get_by_id_for_update(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    limit = get_daily_post_limit(user.plan, user.extended_free)

    today_count = await post_repo.count_today_by_user(db, user_id)
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
    if not getattr(channel, "is_active", True):
        raise HTTPException(status_code=409, detail="Channel is inactive")

    if data.idempotency_key:
        existing = await post_repo.get_by_idempotency_key(
            db, data.channel_id, data.idempotency_key
        )
        if existing is not None:
            return _to_post_response(existing)

    generated_image_key = None
    if data.asset_id is not None:
        asset = await asset_repo.get_owned(db, data.asset_id, user_id)
        if asset is None:
            raise HTTPException(status_code=403, detail="Image asset is not accessible")
        generated_image_key = asset.object_key

    await _check_daily_post_limit(db, user_id)

    post = await post_repo.create(
        db, data.channel_id, data, generated_image_key=generated_image_key
    )
    await db.commit()
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
    asset_id = payload.pop("asset_id", None)
    if asset_id is not None:
        asset = await asset_repo.get_owned(db, asset_id, user_id)
        if asset is None:
            raise HTTPException(status_code=403, detail="Image asset is not accessible")
        payload["generated_asset_id"] = asset.id
        payload["generated_image_key"] = asset.object_key
    content_type = post.content_type
    text_prompt = payload.get("text_prompt", post.text_prompt)
    image_prompt = payload.get("image_prompt", post.image_prompt)
    generated_text = payload.get("generated_text", post.generated_text)
    generated_image_key = payload.get("generated_image_key", post.generated_image_key)
    if content_type == ContentTypeEnum.text and not (text_prompt or generated_text):
        raise HTTPException(status_code=422, detail="Text content is empty")
    if content_type == ContentTypeEnum.image and not (
        image_prompt or generated_image_key
    ):
        raise HTTPException(status_code=422, detail="Image content is empty")
    if content_type == ContentTypeEnum.text_image and not (
        (text_prompt or generated_text) and (image_prompt or generated_image_key)
    ):
        raise HTTPException(
            status_code=422, detail="Text and image content are required"
        )
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


async def trigger_publish(db: AsyncSession, user_id: UUID, post_id: UUID) -> dict:
    await _get_owned_post(db, user_id, post_id)

    from app.tasks.publish_post import publish_post

    task = publish_post.delay(str(post_id))
    logger.info("post_publish_triggered", post_id=str(post_id), user_id=str(user_id))
    return {"post_id": str(post_id), "task_id": task.id, "queued": True}
