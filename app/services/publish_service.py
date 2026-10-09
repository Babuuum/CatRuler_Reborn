from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.models.models import PlatformEnum, PostQueue, PostStatusEnum
from app.core.services import storage
from app.core.services.posters.poster import Platform, PublishResult, SocialPublisher
from app.core.settings import get_settings
from app.repositories import post_repo

PUBLISH_LEASE = timedelta(minutes=5)


class PublishContentError(ValueError):
    """The post cannot be published because its generated content is incomplete."""


def _build_platform(post: PostQueue) -> Platform:
    channel = post.channel
    if channel.platform == PlatformEnum.telegram:
        if channel.tg_config is None:
            raise PublishContentError("Telegram channel config is missing")
        return Platform(
            type="telegram",
            channel_id=channel.tg_config.chat_id,
            token=get_settings().TELEGRAM_BOT_TOKEN,
        )
    if channel.platform == PlatformEnum.vk:
        if channel.vk_config is None:
            raise PublishContentError("VK channel config is missing")
        return Platform(
            type="vk",
            channel_id=channel.vk_config.group_id,
            token=channel.vk_config.community_token,
        )
    raise PublishContentError(f"Unsupported platform: {channel.platform}")


def _content(post: PostQueue) -> tuple[str, str | None]:
    if post.content_type.value in ("text", "text_image") and not post.generated_text:
        raise PublishContentError(
            "Post has no generated text; prompt-only posts require generation first"
        )
    if (
        post.content_type.value in ("image", "text_image")
        and not post.generated_image_key
    ):
        raise PublishContentError("Post has no generated image")
    return post.generated_text or "", post.generated_image_key


def _result_status(results: list[PublishResult]) -> PostStatusEnum:
    if any(result.unknown_outcome for result in results):
        return PostStatusEnum.unknown
    if any(result.success for result in results) and any(
        not result.success for result in results
    ):
        return PostStatusEnum.unknown
    if any(not result.success for result in results):
        return PostStatusEnum.failed
    return PostStatusEnum.sent


async def publish_post(
    db: AsyncSession,
    post_id: UUID,
    owner: str,
    *,
    publisher_factory=SocialPublisher,
) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    post = await post_repo.get_by_id(db, post_id)
    if post is None:
        raise ValueError("Post not found")

    if post.status == PostStatusEnum.in_progress:
        if post.publish_lease_expires_at and post.publish_lease_expires_at < now:
            await post_repo.recover_expired_attempt(db, post_id, now)
        return {
            "post_id": str(post_id),
            "status": PostStatusEnum.unknown.value,
            "skipped": True,
        }
    if post.status != PostStatusEnum.pending:
        return {
            "post_id": str(post_id),
            "status": post.status.value,
            "skipped": True,
        }
    if post.channel is None or not post.channel.is_active:
        await post_repo.fail_pending(db, post_id, "Channel is inactive")
        return {"post_id": str(post_id), "status": PostStatusEnum.failed.value}

    claimed = await post_repo.claim_for_publish(
        db, post_id, owner, now, now + PUBLISH_LEASE
    )
    if claimed is None:
        return {"post_id": str(post_id), "status": "skipped", "skipped": True}

    attempt_id = claimed.publish_attempt_id
    if attempt_id is None:
        raise RuntimeError("Publication claim did not create an attempt")
    try:
        text, image_key = _content(claimed)
        image_bytes = await storage.download_file(image_key) if image_key else None
        publisher = publisher_factory([_build_platform(claimed)])
    except PublishContentError as exc:
        await post_repo.finalize_publish(
            db,
            post_id,
            owner,
            attempt_id,
            PostStatusEnum.failed,
            error_message=str(exc),
        )
        return {"post_id": str(post_id), "status": PostStatusEnum.failed.value}
    except Exception as exc:
        await post_repo.finalize_publish(
            db,
            post_id,
            owner,
            attempt_id,
            PostStatusEnum.failed,
            error_message=f"Publication preparation failed: {type(exc).__name__}",
        )
        return {"post_id": str(post_id), "status": PostStatusEnum.failed.value}

    try:
        results = await publisher.publish(text, image_bytes)
    except Exception as exc:
        await post_repo.finalize_publish(
            db,
            post_id,
            owner,
            attempt_id,
            PostStatusEnum.unknown,
            error_message=f"Provider outcome unknown: {type(exc).__name__}",
        )
        return {"post_id": str(post_id), "status": PostStatusEnum.unknown.value}

    status = _result_status(results)
    first = next((result for result in results if result.success), None)
    try:
        finalized = await post_repo.finalize_publish(
            db,
            post_id,
            owner,
            attempt_id,
            status,
            error_message="; ".join(
                result.error or "provider failure"
                for result in results
                if not result.success
            )
            or None,
            external_post_id=first.post_id if first else None,
            external_post_url=first.post_url if first else None,
        )
    except Exception:
        # The provider has already answered; retrying could duplicate the post.
        await db.rollback()
        return {"post_id": str(post_id), "status": PostStatusEnum.unknown.value}
    if not finalized:
        return {"post_id": str(post_id), "status": PostStatusEnum.unknown.value}
    return {"post_id": str(post_id), "status": status.value}
