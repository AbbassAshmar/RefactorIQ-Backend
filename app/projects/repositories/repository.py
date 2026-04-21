from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.models import Project
from app.schemas.project import ProjectCreate, ProjectResponse


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _to_response(project: Project) -> ProjectResponse:
        return ProjectResponse.model_validate(project)

    def create(self, user_id: uuid.UUID, repo_data: ProjectCreate) -> ProjectResponse:
        project = Project(
            user_id=user_id,
            name=repo_data.name,
            repo_owner=repo_data.repo_owner,
            repo_name=repo_data.repo_name,
            branch=repo_data.branch,
        )
        try:
            self._db.add(project)
            self._db.commit()
            self._db.refresh(project)
            return self._to_response(project)
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateRecordException(
                "Project already exists",
                details={
                    "user_id": str(user_id),
                    "repo_owner": repo_data.repo_owner,
                    "repo_name": repo_data.repo_name,
                    "branch": repo_data.branch,
                },
            ) from exc
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise DatabaseOperationException("Failed to create project") from exc

    def list_by_user_id(self, user_id: uuid.UUID) -> list[ProjectResponse]:
        try:
            stmt = (
                select(Project)
                .where(Project.user_id == user_id)
                .order_by(Project.created_at.desc())
            )
            projects = self._db.execute(stmt).scalars().all()
            return [self._to_response(project) for project in projects]
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to list user projects",
                details={"user_id": str(user_id)},
            ) from exc

    def get_by_id(self, project_id: uuid.UUID) -> ProjectResponse:
        try:
            stmt = select(Project).where(Project.id == project_id)
            project = self._db.execute(stmt).scalar_one_or_none()
            if not project:
                raise RecordNotFoundException(
                    "Project not found",
                    details={"project_id": str(project_id)},
                )
            return self._to_response(project)
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to load project",
                details={"project_id": str(project_id)},
            ) from exc
