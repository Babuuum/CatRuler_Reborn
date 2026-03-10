from celery import Celery

from app.core.logging import setup_logging
from app.core.settings import get_settings

setup_logging()


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "catruler",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        imports=("app.tasks.dispatch_posts", "app.tasks.publish_post"),
        beat_schedule={
            "dispatch-pending-posts": {
                "task": "tasks.dispatch_pending_posts",
                "schedule": 60.0,
            }
        },
    )
    return app


celery_app = make_celery()
