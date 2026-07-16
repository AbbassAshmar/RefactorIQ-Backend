from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
import logging

from app.core.enums import ScanStatus
from app.core.exceptions.domain_exceptions import (
    ConflictError,
    EntityNotFoundError,
    InfrastructureError,
    PersistenceError,
)
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.projects.projects_repository import ProjectRepository
from app.scans.scans_service import ScanService
from app.analysis.services.scan_engine.pipeline.scan_workspace import ScanWorkspaceService
from app.projects.projects_dtos import (
    AdminProjectListFilters,
    AdminProjectListResult,
    AdminProjectOwner,
    AdminProjectResponse,
    ProjectTimelinePoint,
    ProjectTimelineResponse,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
)


logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        scan_service: ScanService,
        workspace_service: ScanWorkspaceService,
    ) -> None:
        self._repo = repository
        self._scan_service = scan_service
        self._workspace_service = workspace_service

    def create_project(self, user_id: uuid.UUID, repo_data: ProjectCreate) -> ProjectResponse:
        try:
            return self._repo.create(user_id, repo_data)
        except DuplicateRecordException as exc:
            raise ConflictError("Project already exists") from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to create project") from exc

    def list_user_projects(self, user_id: uuid.UUID) -> list[ProjectListResponse]:
        try:
            return self._repo.list_by_user_id(user_id)
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list user projects") from exc

    def get_project(self, project_id: uuid.UUID) -> ProjectResponse:
        try:
            return self._repo.get_by_id(project_id)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("project", project_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to retrieve project") from exc
        
    def get_project_by_id(self, project_id: uuid.UUID, user_id: uuid.UUID) -> ProjectResponse:
        try:
            return self._repo.get_by_id_and_user_id(project_id, user_id)
        except RecordNotFoundException as exc:
            logger.warning("Project not found or access denied project_id=%s user_id=%s", project_id, user_id)
            raise EntityNotFoundError("project", project_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to retrieve project") from exc

    def delete_project(self, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
        started = datetime.now(timezone.utc)
        logger.info("[PROJECT DELETE STARTED] project_id=%s user_id=%s", project_id, user_id)
        try:
            context = self._repo.prepare_owned_deletion(project_id, user_id)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("project", project_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to prepare project deletion") from exc
        cancellation_outcomes: dict[uuid.UUID, bool] = {}
        try:
            cancellation_outcomes = self._scan_service.request_scan_cancellations(
                list(context.active_scan_ids)
            )
            self._scan_service.forget_scan_results(list(context.scan_ids))
            for scan_id in context.scan_ids:
                logger.info("[PROJECT DELETE WORKSPACE] project_id=%s scan_id=%s", project_id, scan_id)
                try:
                    self._workspace_service.delete_by_scan_id(scan_id)
                except FileNotFoundError:
                    logger.debug("[PROJECT DELETE WORKSPACE ABSENT] project_id=%s scan_id=%s", project_id, scan_id)
                except OSError as exc:
                    logger.exception(
                        "[PROJECT DELETE WORKSPACE FAILED] project_id=%s scan_id=%s",
                        project_id,
                        scan_id,
                    )
                    raise InfrastructureError(
                        "Unable to clean project scan workspace",
                        details={"project_id": str(project_id), "scan_id": str(scan_id)},
                    ) from exc

            self._repo.delete_prepared_project(context, user_id)
        except RecordNotFoundException as exc:
            self._abort_project_deletion(context)
            raise EntityNotFoundError("project", project_id) from exc
        except DatabaseOperationException as exc:
            self._abort_project_deletion(context)
            raise PersistenceError("Unable to delete project") from exc
        except Exception:
            self._abort_project_deletion(context)
            raise

        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        logger.info(
            "[PROJECT DELETE COMPLETED] project_id=%s project_name=%s user_id=%s scan_count=%d active_scan_count=%d revoke_failures=%d elapsed_seconds=%.3f",
            project_id,
            context.project_name,
            user_id,
            len(context.scan_ids),
            len(context.active_scan_ids),
            sum(not outcome for outcome in cancellation_outcomes.values()),
            elapsed,
        )

    def _abort_project_deletion(self, context) -> None:
        self._repo.abort_prepared_deletion()
        if not context.active_scan_ids:
            return
        try:
            for scan_id in context.active_scan_ids:
                self._scan_service.transition_scan_status(
                    scan_id,
                    ScanStatus.CANCELLED,
                    expected_statuses={ScanStatus.PENDING, ScanStatus.RUNNING},
                )
        except Exception:
            logger.exception(
                "[PROJECT DELETE COMPENSATION FAILED] project_id=%s",
                context.project_id,
            )

    def list_admin_projects(
        self,
        filters: AdminProjectListFilters,
    ) -> AdminProjectListResult:
        try:
            rows, total_count = self._repo.list_admin_projects(filters)
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list administrative projects") from exc
        return AdminProjectListResult(
            items=[
                AdminProjectResponse(
                    id=row.id,
                    user_id=row.user_id,
                    name=row.name,
                    repo_owner=row.repo_owner,
                    repo_name=row.repo_name,
                    branch=row.branch,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    owner=AdminProjectOwner(
                        id=row.owner_id,
                        username=row.owner_username,
                        email=row.owner_email,
                    ),
                    scan_count=row.scan_count,
                    average_scan_duration_seconds=row.average_scan_duration_seconds,
                )
                for row in rows
            ],
            total_count=total_count,
        )

    def get_projects_over_time(
        self,
        *,
        now: datetime | None = None,
    ) -> ProjectTimelineResponse:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        else:
            current = current.astimezone(timezone.utc)

        current_month = date(current.year, current.month, 1)
        start_month = self._shift_month(current_month, -14)
        next_month = self._shift_month(current_month, 1)
        created_from = datetime.combine(start_month, time.min, tzinfo=timezone.utc)
        created_before = datetime.combine(next_month, time.min, tzinfo=timezone.utc)

        try:
            projects = self._repo.list_created_at_between(
                created_from=created_from,
                created_before=created_before,
            )
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to load projects over time") from exc

        counts = {self._shift_month(start_month, offset): 0 for offset in range(15)}
        for created_at in projects:
            created = (
                created_at.replace(tzinfo=timezone.utc)
                if created_at.tzinfo is None
                else created_at.astimezone(timezone.utc)
            )
            month = date(created.year, created.month, 1)
            if month in counts:
                counts[month] += 1

        return ProjectTimelineResponse(
            points=[
                ProjectTimelinePoint(date=month, count=counts[month])
                for month in counts
            ]
        )

    @staticmethod
    def _shift_month(month: date, offset: int) -> date:
        month_index = month.year * 12 + month.month - 1 + offset
        year, zero_based_month = divmod(month_index, 12)
        return date(year, zero_based_month + 1, 1)
