from datetime import UTC, datetime

from billiard.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.repositories import post_repo
from app.tasks.publish_post import _get_session_factory, publish_post

logger = get_task_logger(__name__)


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
        session_factory = _get_session_factory()
        now = datetime.now(UTC)
        with session_factory() as db:
            posts = post_repo.get_due_pending_sync(db, now)

        dispatched = []
        for post in posts:
            task = publish_post.delay(str(post.id))
            dispatched.append({"post_id": str(post.id), "task_id": task.id})

        logger.info(
            "dispatch_pending_posts_completed",
            task_id=self.request.id,
            count=len(dispatched),
        )
        return {"count": len(dispatched), "dispatched": dispatched}
    except SoftTimeLimitExceeded as exc:
        logger.error(
            "dispatch_pending_posts_soft_time_limit",
            task_id=self.request.id,
        )
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception(
            "dispatch_pending_posts_exception",
            task_id=self.request.id,
        )
        raise self.retry(exc=exc)
