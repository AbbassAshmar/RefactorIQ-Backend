from celery import Task, shared_task
from uuid import UUID
import logging

from app.analysis.dependencies import provide_scan_engine_service
from app.analysis.services.scan_engine.scan_engine_service import ScanEngineService
from app.core.enums import ScanStatus
from app.scans.dependencies import provide_scan_service

logger = logging.getLogger(__name__)


class ScanTask(Task):
    """
    Base task for all scan jobs.

    Lifecycle (per attempt):
        1. run()          → on_scan_started() fires
        2a. [success]     → on_success() fires
        2b. [retriable]   → on_retry() fires
        2c. [terminal]    → on_failure() fires

    Custom handlers (on_scan_*) own the business logic.
    Celery hooks are thin dispatchers only — no logic lives here.
    """

    abstract = True  # prevents Celery from registering this as a task itself

    # ── Celery lifecycle hooks (dispatchers only) ─────────────────────────────

    def on_success(self, retval, task_id, args, kwargs):
        scan_id = self._extract_scan_id(args)
        on_scan_succeeded(self, scan_id)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        scan_id = self._extract_scan_id(args)
        on_scan_attempt_failed(self, scan_id, exc, is_terminal=False)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        scan_id = self._extract_scan_id(args)
        on_scan_attempt_failed(self, scan_id, exc, is_terminal=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_scan_id(args: tuple) -> UUID | None:
        try:
            return UUID(args[0]) if args else None
        except (ValueError, AttributeError):
            logger.warning("Could not extract scan_id from args: %s", args)
            return None


@shared_task(
    base=ScanTask,
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    queue="scans",
)
def run_project_scan(self, scan_id: str):
    """
    Task body is pure orchestration — no lifecycle management here.
    All success/failure/retry handling is owned by ScanTask hooks above.
    """
    scan_uuid = UUID(scan_id)

    on_scan_started(self, scan_uuid)
    with provide_scan_engine_service() as scan_engine_service:
        run_scan_pipeline(scan_uuid, scan_engine_service=scan_engine_service)


# ── Business logic handlers ───────────────────────────────────────────────────
# These are plain functions — easy to unit-test without Celery infrastructure.

def on_scan_started(task: ScanTask, scan_id: UUID | None) -> None:
    """Fires at the top of every attempt, including retries."""
    logger.info(
        "[SCAN STARTED] scan_id=%s attempt=%d/%d",
        scan_id,
        task.request.retries + 1,
        task.max_retries + 1,
    )
    if scan_id is None:
        logger.error("Cannot mark scan as running without a scan_id")
        return
    with provide_scan_service() as scan_service:
        scan_service.update_scan_status(scan_id, ScanStatus.RUNNING)
    logger.info("[SCAN STATUS UPDATED] scan_id=%s status=%s", scan_id, ScanStatus.RUNNING.value)


def on_scan_succeeded(task: ScanTask, scan_id: UUID | None) -> None:
    """Fires once, only on a clean completion."""
    logger.info(
        "[SCAN SUCCEEDED] scan_id=%s task_id=%s",
        scan_id,
        task.request.id,
    )
    if scan_id is None:
        logger.error("Cannot mark scan as succeeded without a scan_id")
        return
    with provide_scan_service() as scan_service:
        scan_service.update_scan_status(scan_id, ScanStatus.SUCCEEDED)
    logger.info("[SCAN STATUS UPDATED] scan_id=%s status=%s", scan_id, ScanStatus.SUCCEEDED.value)


def on_scan_attempt_failed(
    task: ScanTask,
    scan_id: UUID | None,
    exc: Exception,
    *,
    is_terminal: bool,
) -> None:
    """
    Fires on every failure.
    is_terminal=False → this attempt will be retried.
    is_terminal=True  → all retries exhausted, permanent failure.
    """
    if is_terminal:
        logger.error(
            "[SCAN FAILED - PERMANENT] scan_id=%s attempt=%d/%d error=%s",
            scan_id,
            task.request.retries + 1,
            task.max_retries + 1,
            str(exc),
            exc_info=True,
        )
        if scan_id is not None:
            try:
                with provide_scan_service() as scan_service:
                    scan_service.update_scan_status(scan_id, ScanStatus.FAILED)
                logger.info("[SCAN STATUS UPDATED] scan_id=%s status=%s", scan_id, ScanStatus.FAILED.value)
            except Exception:
                logger.exception("Failed to persist terminal scan status for scan_id=%s", scan_id)
    else:
        logger.warning(
            "[SCAN FAILED - RETRYING] scan_id=%s attempt=%d/%d error=%s",
            scan_id,
            task.request.retries + 1,
            task.max_retries + 1,
            str(exc),
            exc_info=True,
        )
        # There is no RETRYING enum; the scan remains RUNNING until the next attempt.


def run_scan_pipeline(
    scan_id: UUID,
    *,
    scan_engine_service: ScanEngineService,
) -> None:
    logger.info("[SCAN PIPELINE] scan_id=%s", scan_id)
    scan_engine_service.execute_scan(scan_id)
    # throw error for testing retry logic

    
