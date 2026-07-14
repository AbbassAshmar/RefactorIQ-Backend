from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from app.core.exceptions.domain_exceptions import (
    ConflictError,
    EntityNotFoundError,
    PersistenceError,
)
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.projects.projects_repository import ProjectRepository
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


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self._repo = repository

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
            print("Project not found or access denied")
            raise EntityNotFoundError("project", project_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to retrieve project") from exc

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
