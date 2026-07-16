from celery import Celery
from kombu import Queue

from app.core.logger import configure_logging

configure_logging()

celery = Celery(
    "worker",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/1",
    include=["app.workers.scan_worker"],
)

celery.conf.update(
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("scans"),
    ),

    task_routes={
        "app.workers.scan_worker.run_project_scan": {
            "queue": "scans"
        }
    },

    task_track_started=True,

    # Scan tasks are deliberately at-most-once. A failed task must be
    # acknowledged and never re-delivered after a worker process is lost.
    task_acks_late=False,
    task_reject_on_worker_lost=False,
    worker_send_task_events = True,

    worker_prefetch_multiplier=1,
    worker_disable_prefetch=True,

    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)
