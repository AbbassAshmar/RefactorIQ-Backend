from uuid import UUID

from app.core.celery_app import celery
from app.core.exceptions.domain_exceptions import QueueError


class ScansQueueService:
    TASK_NAME = (
        "app.workers.scan_worker.run_project_scan"
    )

    QUEUE_NAME = "scans"

    def enqueue_scan(self, scan_id: UUID):
        try:
            task_result = celery.send_task(
                self.TASK_NAME,
                args=[str(scan_id)],
                queue=self.QUEUE_NAME,
            )
            return task_result
        except Exception as exc:
            raise QueueError(
                message="Failed to enqueue scan",
                details={"scan_id": str(scan_id), "queue": self.QUEUE_NAME},
            ) from exc

    def enqueue_project_scan_job(self, scan_id: UUID) -> None:
        self.enqueue_scan(scan_id)