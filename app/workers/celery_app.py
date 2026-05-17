from celery import Celery

from app.config import settings

broker_url = settings.redis_url or "redis://localhost:6379/0"
result_backend = settings.celery_result_backend or broker_url

celery_app = Celery(
    "botbet",
    broker=broker_url,
    backend=result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    timezone=settings.timezone,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_routes={
        "app.workers.tasks.analyze_match_task": {"queue": "analysis"},
        "app.workers.tasks.send_telegram_task": {"queue": "telegram"},
        "app.workers.tasks.run_scheduler_tick_task": {"queue": "scheduler"},
    },
)
