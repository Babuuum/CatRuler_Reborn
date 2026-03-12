from importlib.util import find_spec
from uuid import UUID

import boto3
from billiard.exceptions import SoftTimeLimitExceeded
from celery.exceptions import MaxRetriesExceededError
from celery.utils.log import get_task_logger
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.celery_app import celery_app
from app.core.db.models.models import PlatformEnum, PostStatusEnum
from app.core.services.posters.poster import Platform, SocialPublisher
from app.core.settings import get_settings
from app.repositories import post_repo

logger = get_task_logger(__name__)

_session_factory: sessionmaker[Session] | None = None


def _require_sync_driver(sync_database_url: str) -> None:
    if sync_database_url.startswith("postgresql://") and not (
        find_spec("psycopg") or find_spec("psycopg2")
    ):
        raise RuntimeError(
            "A sync PostgreSQL driver is required for Celery tasks. "
            "Install psycopg or psycopg2-binary."
        )


def _get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        settings = get_settings()
        _require_sync_driver(settings.sync_database_url)
        engine = create_engine(settings.sync_database_url, pool_pre_ping=True)
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _session_factory


def _download_image(image_key: str) -> bytes:
    settings = get_settings()
    s3 = boto3.client(
        "s3",
        endpoint_url="https://storage.yandexcloud.net",
        aws_access_key_id=settings.YANDEX_ACCESS_KEY,
        aws_secret_access_key=settings.YANDEX_SECRET_KEY,
    )
    response = s3.get_object(Bucket=settings.YANDEX_BUCKET_NAME, Key=image_key)
    return response["Body"].read()


def _build_platform(post) -> Platform:
    channel = post.channel
    if channel.platform == PlatformEnum.telegram:
        if channel.tg_config is None:
            raise ValueError("Telegram channel config is missing")
        return Platform(
            type="telegram",
            channel_id=channel.tg_config.chat_id,
            token=get_settings().TELEGRAM_BOT_TOKEN,
        )

    if channel.platform == PlatformEnum.vk:
        if channel.vk_config is None:
            raise ValueError("VK channel config is missing")
        return Platform(
            type="vk",
            channel_id=channel.vk_config.group_id,
            token=channel.vk_config.community_token,
        )

    raise ValueError(f"Unsupported platform: {channel.platform}")


def _get_post_text(post) -> str:
    return post.generated_text or post.text_prompt or ""


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=150,
    name="tasks.publish_post",
)
def publish_post(self, post_id: str) -> dict:
    session_factory = _get_session_factory()
    post_uuid = UUID(post_id)

    try:
        with session_factory() as db:
            post = post_repo.get_by_id_sync(db, post_uuid)
            if post is None:
                raise ValueError("Post not found")

            image_bytes = (
                _download_image(post.generated_image_key)
                if post.generated_image_key
                else None
            )
            publisher = SocialPublisher([_build_platform(post)])
            results = publisher.publish_sync(_get_post_text(post), image_bytes)

            failed = [result for result in results if not result.success]
            if failed:
                error_message = "; ".join(
                    result.error or "unknown error" for result in failed
                )
                post_repo.update_status_sync(
                    db,
                    post_uuid,
                    PostStatusEnum.failed,
                    error_message=error_message,
                )
                logger.error(
                    "publish_post_failed task_id=%s post_id=%s channel_id=%s error=%s",
                    self.request.id,
                    post_id,
                    str(post.channel_id),
                    error_message,
                )
                return {
                    "post_id": post_id,
                    "status": PostStatusEnum.failed.value,
                    "results": [result.__dict__ for result in results],
                }

            post_repo.update_status_sync(db, post_uuid, PostStatusEnum.sent)
            logger.info(
                "publish_post_sent task_id=%s post_id=%s channel_id=%s",
                self.request.id,
                post_id,
                str(post.channel_id),
            )
            return {
                "post_id": post_id,
                "status": PostStatusEnum.sent.value,
                "results": [result.__dict__ for result in results],
            }
    except SoftTimeLimitExceeded as exc:
        logger.error(
            "publish_post_soft_time_limit task_id=%s post_id=%s",
            self.request.id,
            post_id,
        )
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception(
            "publish_post_exception task_id=%s post_id=%s",
            self.request.id,
            post_id,
        )
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            with session_factory() as db:
                post = post_repo.get_by_id_sync(db, post_uuid)
                if post is not None:
                    post_repo.update_status_sync(
                        db,
                        post_uuid,
                        PostStatusEnum.failed,
                        error_message=str(exc),
                    )
            raise
