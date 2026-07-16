from uuid import UUID
import logging

from app.core.celery_app import celery
from app.core.exceptions.domain_exceptions import QueueError


logger = logging.getLogger(__name__)


class ScansQueueService:
    TASK_NAME = (
        "app.workers.scan_worker.run_project_scan"
    )

    QUEUE_NAME = "scans"

    def enqueue_scan(self, scan_id: UUID):
        try:
            logger.info("[SCAN QUEUE ENQUEUE] scan_id=%s queue=%s", scan_id, self.QUEUE_NAME)
            task_result = celery.send_task(
                self.TASK_NAME,
                args=[str(scan_id)],
                task_id=str(scan_id),
                queue=self.QUEUE_NAME,
            )
            logger.info(
                "[SCAN QUEUE ENQUEUED] scan_id=%s task_id=%s queue=%s",
                scan_id,
                task_result.id,
                self.QUEUE_NAME,
            )
            return task_result
        except Exception as exc:
            logger.exception("[SCAN QUEUE ENQUEUE FAILED] scan_id=%s queue=%s", scan_id, self.QUEUE_NAME)
            raise QueueError(
                message="Failed to enqueue scan",
                details={"scan_id": str(scan_id), "queue": self.QUEUE_NAME},
            ) from exc

    def enqueue_project_scan_job(self, scan_id: UUID) -> None:
        self.enqueue_scan(scan_id)

    def request_scan_cancellation(self, scan_id: UUID) -> bool:
        """Revoke a pending/running scan without blocking project deletion."""
        try:
            logger.info("[SCAN QUEUE REVOKE] scan_id=%s task_id=%s", scan_id, scan_id)
            celery.control.revoke(
                str(scan_id),
                terminate=True,
                signal="SIGTERM",
            )
            logger.info("[SCAN QUEUE REVOKE REQUESTED] scan_id=%s task_id=%s", scan_id, scan_id)
            return True
        except Exception:
            logger.exception("[SCAN QUEUE REVOKE FAILED] scan_id=%s task_id=%s", scan_id, scan_id)
            return False

    def forget_scan_result(self, scan_id: UUID) -> bool:
        try:
            celery.AsyncResult(str(scan_id)).forget()
            logger.debug("[SCAN QUEUE RESULT FORGOTTEN] scan_id=%s", scan_id)
            return True
        except Exception:
            logger.exception("[SCAN QUEUE RESULT FORGET FAILED] scan_id=%s", scan_id)
            return False
