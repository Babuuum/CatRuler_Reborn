import asyncio
from datetime import UTC, datetime

from billiard.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.core.settings import get_settings
from app.repositories import post_repo
from app.tasks.publish_post import publish_post

logger = get_task_logger(__name__)


async def _due_posts():
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await post_repo.get_due_pending(
                db, datetime.now(UTC).replace(tzinfo=None)
            )
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=60,
    time_limit=90,
    name="tasks.dispatch_pending_posts",
)
def dispatch_pending_posts(self) -> dict:
    try:
        posts = asyncio.run(_due_posts())
        dispatched = [
            {"post_id": str(post.id), "task_id": publish_post.delay(str(post.id)).id}
            for post in posts
        ]
        logger.info(
            "dispatch_pending_posts_completed task_id=%s count=%s",
            self.request.id,
            len(dispatched),
        )
        return {"count": len(dispatched), "dispatched": dispatched}
    except SoftTimeLimitExceeded as exc:
        logger.error(
            "dispatch_pending_posts_soft_time_limit task_id=%s", self.request.id
        )
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("dispatch_pending_posts_exception task_id=%s", self.request.id)
        raise self.retry(exc=exc)
