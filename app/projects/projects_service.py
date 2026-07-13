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
from app.projects.projects_dtos import ProjectCreate, ProjectResponse


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
