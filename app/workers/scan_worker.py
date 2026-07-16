from celery import Task, shared_task
from celery.exceptions import Ignore
from uuid import UUID
import logging

from app.analysis.dependencies import provide_scan_engine_service
from app.analysis.services.scan_engine.scan_engine_service import ScanEngineService
from app.core.enums import ScanStatus
from app.core.exceptions.domain_exceptions import EntityNotFoundError
from app.scans.dependencies import provide_scan_service

logger = logging.getLogger(__name__)


class ScanTask(Task):
    """
    Base task for all scan jobs.

    Lifecycle:
        1. run()          → on_scan_started() fires
        2a. [success]     → on_success() fires
        2b. [failure]     → on_failure() fires exactly once

    Custom handlers (on_scan_*) own the business logic.
    Celery hooks are thin dispatchers only — no logic lives here.
    """

    abstract = True  # prevents Celery from registering this as a task itself

    # ── Celery lifecycle hooks (dispatchers only) ─────────────────────────────

    def on_success(self, retval, task_id, args, kwargs):
        scan_id = self._extract_scan_id(args)
        on_scan_succeeded(self, scan_id)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        scan_id = self._extract_scan_id(args)
        on_scan_failed(self, scan_id, exc)

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
    max_retries=0,
    acks_late=False,
    reject_on_worker_lost=False,
    ignore_result=True,
    queue="scans",
)
def run_project_scan(self, scan_id: str):
    """
    Task body is pure orchestration — no retry or terminal-state management
    lives here. ScanTask hooks own the lifecycle persistence.
    """
    scan_uuid = UUID(scan_id)

    on_scan_started(self, scan_uuid)
    with provide_scan_engine_service() as scan_engine_service:
        run_scan_pipeline(scan_uuid, scan_engine_service=scan_engine_service)


# ── Business logic handlers ───────────────────────────────────────────────────
# These are plain functions — easy to unit-test without Celery infrastructure.

def on_scan_started(task: ScanTask, scan_id: UUID | None) -> None:
    """Mark a scan as running before the pipeline starts."""
    logger.info(
        "[SCAN STARTED] scan_id=%s task_id=%s",
        scan_id,
        task.request.id,
    )
    if scan_id is None:
        logger.error("Cannot mark scan as running without a scan_id")
        raise Ignore()
    with provide_scan_service() as scan_service:
        try:
            transitioned = scan_service.transition_scan_status(
                scan_id,
                ScanStatus.RUNNING,
                expected_statuses={ScanStatus.PENDING},
            )
        except EntityNotFoundError:
            logger.warning("[SCAN SKIPPED] scan_id=%s no longer exists; likely project deletion", scan_id)
            raise Ignore()
        except Exception:
            logger.exception("[SCAN STATUS FAILED] scan_id=%s status=%s", scan_id, ScanStatus.RUNNING.value)
            raise
    if not transitioned:
        logger.warning(
            "[SCAN SKIPPED] scan_id=%s task_id=%s is no longer pending; no pipeline will run",
            scan_id,
            task.request.id,
        )
        raise Ignore()
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
        try:
            transitioned = scan_service.transition_scan_status(
                scan_id,
                ScanStatus.SUCCEEDED,
                expected_statuses={ScanStatus.RUNNING},
            )
        except EntityNotFoundError:
            logger.warning("[SCAN STATUS SKIPPED] scan_id=%s no longer exists", scan_id)
            return
        except Exception:
            logger.exception("[SCAN STATUS FAILED] scan_id=%s status=%s", scan_id, ScanStatus.SUCCEEDED.value)
            return
    if transitioned:
        logger.info("[SCAN STATUS UPDATED] scan_id=%s status=%s", scan_id, ScanStatus.SUCCEEDED.value)
    else:
        logger.info("[SCAN STATUS SKIPPED] scan_id=%s status=%s", scan_id, ScanStatus.SUCCEEDED.value)


def on_scan_failed(
    task: ScanTask,
    scan_id: UUID | None,
    exc: Exception,
) -> None:
    """Persist one terminal failure; Celery never retries this task."""
    logger.error(
        "[SCAN FAILED - TERMINAL] scan_id=%s task_id=%s error=%s",
        scan_id,
        task.request.id,
        str(exc) or exc.__class__.__name__,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    if scan_id is None:
        logger.error("Cannot mark failed scan without a scan_id")
        return
    try:
        with provide_scan_service() as scan_service:
            transitioned = scan_service.transition_scan_status(
                scan_id,
                ScanStatus.FAILED,
                expected_statuses={ScanStatus.PENDING, ScanStatus.RUNNING},
                error_message=str(exc) or exc.__class__.__name__,
            )
        if transitioned:
            logger.info("[SCAN STATUS UPDATED] scan_id=%s status=%s", scan_id, ScanStatus.FAILED.value)
        else:
            logger.info("[SCAN STATUS SKIPPED] scan_id=%s status=%s", scan_id, ScanStatus.FAILED.value)
    except EntityNotFoundError:
        logger.warning("[SCAN STATUS SKIPPED] scan_id=%s no longer exists", scan_id)
    except Exception:
        logger.exception("Failed to persist terminal scan status for scan_id=%s", scan_id)


def on_scan_attempt_failed(
    task: ScanTask,
    scan_id: UUID | None,
    exc: Exception,
    *,
    is_terminal: bool,
) -> None:
    """Backward-compatible test/helper entry point; retries are never scheduled."""
    if not is_terminal:
        logger.warning(
            "[SCAN FAILED - NO RETRY] scan_id=%s task_id=%s error=%s",
            scan_id,
            getattr(task.request, "id", None),
            str(exc) or exc.__class__.__name__,
        )
        return
    logger.error(
        "[SCAN FAILED - TERMINAL] scan_id=%s error=%s",
        scan_id,
        str(exc) or exc.__class__.__name__,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    if scan_id is None:
        return
    try:
        with provide_scan_service() as scan_service:
            scan_service.update_scan_status(
                scan_id,
                ScanStatus.FAILED,
                error_message=str(exc) or exc.__class__.__name__,
            )
    except Exception:
        logger.exception("Failed to persist terminal scan status for scan_id=%s", scan_id)


def run_scan_pipeline(
    scan_id: UUID,
    *,
    scan_engine_service: ScanEngineService,
) -> None:
    logger.info("[SCAN PIPELINE] scan_id=%s", scan_id)
    scan_engine_service.execute_scan(scan_id)

    
