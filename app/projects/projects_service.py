from __future__ import annotations

import uuid

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
    ProjectCreate,
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

    def list_user_projects(self, user_id: uuid.UUID) -> list[ProjectResponse]:
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
