from __future__ import annotations

import uuid

from app.core.exceptions.domain_exceptions import ConflictError, EntityNotFoundError
from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.projects.repositories.repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectResponse


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self._repo = repository

    def create_project(self, user_id: uuid.UUID, repo_data: ProjectCreate) -> ProjectResponse:
        try:
            return self._repo.create(user_id, repo_data)
        except DuplicateRecordException as exc:
            raise ConflictError("Project already exists") from exc
        except DatabaseOperationException as exc:
            raise ConflictError("Unable to create project") from exc

    def list_user_projects(self, user_id: uuid.UUID) -> list[ProjectResponse]:
        try:
            return self._repo.list_by_user_id(user_id)
        except DatabaseOperationException as exc:
            raise ConflictError("Unable to list user projects") from exc

    def get_project(self, project_id: uuid.UUID) -> ProjectResponse:
        try:
            return self._repo.get_by_id(project_id)
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("project", project_id) from exc
        except DatabaseOperationException as exc:
            raise ConflictError("Unable to retrieve project") from exc
