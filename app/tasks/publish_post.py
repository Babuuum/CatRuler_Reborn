import asyncio
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded
from celery.exceptions import MaxRetriesExceededError
from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.core.db.models.models import PostStatusEnum
from app.core.settings import get_settings
from app.repositories import post_repo
from app.services import publish_service

logger = get_task_logger(__name__)


async def _with_session(callback):
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await callback(db)
    finally:
        await engine.dispose()


async def _mark_status(post_id: UUID) -> None:
    async def callback(db):
        post = await post_repo.get_by_id(db, post_id)
        if post is not None and post.status == PostStatusEnum.in_progress:
            await post_repo.mark_unknown(db, post_id, "Publication outcome unknown")

    await _with_session(callback)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=120,
    time_limit=150,
    name="tasks.publish_post",
)
def publish_post(self, post_id: str) -> dict:
    post_uuid = UUID(post_id)
    owner = str(self.request.id)
    try:
        result = asyncio.run(
            _with_session(lambda db: publish_service.publish_post(db, post_uuid, owner))
        )
        logger.info(
            "publish_post_completed task_id=%s post_id=%s status=%s",
            self.request.id,
            post_id,
            result.get("status"),
        )
        return result
    except SoftTimeLimitExceeded as exc:
        asyncio.run(_mark_status(post_uuid))
        logger.error(
            "publish_post_soft_time_limit task_id=%s post_id=%s",
            self.request.id,
            post_id,
        )
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise
    except Exception as exc:
        logger.exception(
            "publish_post_exception task_id=%s post_id=%s",
            self.request.id,
            post_id,
        )
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            asyncio.run(_mark_status(post_uuid))
            raise
