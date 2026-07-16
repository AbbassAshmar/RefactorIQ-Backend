from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions.repository_exceptions import (
    DatabaseOperationException,
    DuplicateRecordException,
    RecordNotFoundException,
)
from app.core.enums import ScanStatus
from app.models import Project, Scan, User
from app.projects.projects_dtos import (
    AdminProjectListFilters,
    AdminProjectRow,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectDeletionContext,
)

import logging
logger = logging.getLogger(__name__)

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

    def list_by_user_id(self, user_id: uuid.UUID) -> list[ProjectListResponse]:
        try:
            latest_scan_status = (
                select(Scan.status)
                .where(Scan.project_id == Project.id)
                .order_by(Scan.created_at.desc(), Scan.id.desc())
                .limit(1)
                .scalar_subquery()
            )
            running_scan_exists = select(Scan.id).where(
                Scan.project_id == Project.id,
                Scan.status == ScanStatus.RUNNING,
            ).exists()
            project_status = case(
                (running_scan_exists, ScanStatus.RUNNING),
                else_=latest_scan_status,
            ).label("status")
            stmt = (
                select(Project, project_status)
                .where(Project.user_id == user_id)
                .order_by(Project.created_at.desc())
            )
            projects = self._db.execute(stmt).all()
            return [
                ProjectListResponse(
                    **self._to_response(project).model_dump(),
                    status=status,
                )
                for project, status in projects
            ]
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
    
    def get_by_id_and_user_id(self, project_id: uuid.UUID, user_id: uuid.UUID) -> ProjectResponse:
        try:
            logger.info(f"Loading project with ID {project_id} for user {user_id}")
            stmt = select(Project).where(Project.id == project_id, Project.user_id == user_id)
            project = self._db.execute(stmt).scalar_one_or_none()
            if not project:
                raise RecordNotFoundException(
                    "Project not found",
                    details={"project_id": str(project_id), "user_id": str(user_id)},
                )
            return self._to_response(project)
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseOperationException(
                "Failed to load project",
                details={"project_id": str(project_id), "user_id": str(user_id)},
            ) from exc

    def prepare_owned_deletion(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ProjectDeletionContext:
        """Lock a project and its scans until deletion or rollback completes."""
        try:
            logger.info(
                "Preparing project deletion project_id=%s user_id=%s",
                project_id,
                user_id,
            )
            project = self._db.execute(
                select(Project)
                .where(Project.id == project_id, Project.user_id == user_id)
                .with_for_update()
            ).scalar_one_or_none()
            if project is None:
                raise RecordNotFoundException(
                    "Project not found",
                    details={"project_id": str(project_id), "user_id": str(user_id)},
                )

            scan_rows = self._db.execute(
                select(Scan.id, Scan.status)
                .where(Scan.project_id == project_id)
                .with_for_update()
            ).all()
            scan_ids = tuple(row[0] for row in scan_rows)
            active_scan_ids = tuple(
                row[0]
                for row in scan_rows
                if (row[1] if isinstance(row[1], ScanStatus) else ScanStatus(row[1]))
                in {ScanStatus.PENDING, ScanStatus.RUNNING}
            )
            logger.info(
                "Prepared project deletion project_id=%s scan_count=%d active_scan_count=%d",
                project_id,
                len(scan_ids),
                len(active_scan_ids),
            )
            return ProjectDeletionContext(
                project_id=project_id,
                project_name=project.name,
                scan_ids=scan_ids,
                active_scan_ids=active_scan_ids,
            )
        except RecordNotFoundException:
            raise
        except (SQLAlchemyError, ValueError) as exc:
            self._db.rollback()
            logger.exception("Failed to prepare project deletion project_id=%s", project_id)
            raise DatabaseOperationException(
                "Failed to prepare project deletion",
                details={"project_id": str(project_id)},
            ) from exc

    def delete_prepared_project(self, context: ProjectDeletionContext, user_id: uuid.UUID) -> None:
        try:
            result = self._db.execute(
                delete(Project).where(
                    Project.id == context.project_id,
                    Project.user_id == user_id,
                )
            )
            if result.rowcount != 1:
                raise RecordNotFoundException(
                    "Project not found",
                    details={"project_id": str(context.project_id), "user_id": str(user_id)},
                )
            self._db.commit()
            logger.info(
                "Deleted project row project_id=%s cascaded_scan_count=%d",
                context.project_id,
                len(context.scan_ids),
            )
        except RecordNotFoundException:
            self._db.rollback()
            raise
        except SQLAlchemyError as exc:
            self._db.rollback()
            logger.exception("Failed to delete project project_id=%s", context.project_id)
            raise DatabaseOperationException(
                "Failed to delete project",
                details={"project_id": str(context.project_id)},
            ) from exc

    def abort_prepared_deletion(self) -> None:
        logger.info("Rolling back prepared project deletion")
        self._db.rollback()

    def count_projects(
        self,
        *,
        created_from: datetime | None = None,
        created_before: datetime | None = None,
    ) -> int:
        """Count projects, optionally within a half-open creation-time window."""
        try:
            statement = select(func.count(Project.id))
            if created_from is not None:
                statement = statement.where(Project.created_at >= created_from)
            if created_before is not None:
                statement = statement.where(Project.created_at < created_before)
            return int(self._db.execute(statement).scalar_one() or 0)
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to count projects") from exc

    def list_created_at_between(
        self,
        *,
        created_from: datetime,
        created_before: datetime,
    ) -> list[datetime]:
        try:
            statement = (
                select(Project.created_at)
                .where(
                    Project.created_at >= created_from,
                    Project.created_at < created_before,
                )
            )
            return list(self._db.execute(statement).scalars().all())
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to aggregate projects over time") from exc

    def list_admin_projects(
        self,
        filters: AdminProjectListFilters,
    ) -> tuple[list[AdminProjectRow], int]:
        """List projects across all users with scan aggregates."""
        try:
            valid_duration = (
                Scan.started_at.is_not(None)
                & Scan.finished_at.is_not(None)
                & (Scan.finished_at >= Scan.started_at)
            )
            duration_seconds = case(
                (
                    valid_duration,
                    func.extract("epoch", Scan.finished_at)
                    - func.extract("epoch", Scan.started_at),
                ),
                else_=None,
            )
            scan_count = func.count(Scan.id)
            average_duration = func.avg(duration_seconds)

            conditions = []
            if filters.query and filters.query.strip():
                conditions.append(Project.name.ilike(f"%{filters.query.strip()}%"))

            statement = (
                select(
                    Project.id,
                    Project.user_id,
                    Project.name,
                    Project.repo_owner,
                    Project.repo_name,
                    Project.branch,
                    Project.created_at,
                    Project.updated_at,
                    User.id,
                    User.username,
                    User.email,
                    scan_count,
                    average_duration,
                )
                .join(User, Project.user_id == User.id)
                .outerjoin(Scan, Scan.project_id == Project.id)
                .where(*conditions)
                .group_by(
                    Project.id,
                    Project.user_id,
                    Project.name,
                    Project.repo_owner,
                    Project.repo_name,
                    Project.branch,
                    Project.created_at,
                    Project.updated_at,
                    User.id,
                    User.username,
                    User.email,
                )
            )

            sort_expressions = {
                "created_at": Project.created_at,
                "name": func.lower(Project.name),
                "owner": func.lower(User.username),
                "scan_count": scan_count,
                "scan_duration": average_duration,
            }
            sort_expression = sort_expressions[filters.sort_by]
            ordering = (
                sort_expression.desc()
                if filters.sort_order == "desc"
                else sort_expression.asc()
            )
            if filters.sort_by == "scan_duration":
                ordering = ordering.nullslast()
            id_ordering = (
                Project.id.desc()
                if filters.sort_order == "desc"
                else Project.id.asc()
            )
            statement = (
                statement.order_by(ordering, id_ordering)
                .offset((filters.page - 1) * filters.limit)
                .limit(filters.limit)
            )

            total = int(
                self._db.execute(
                    select(func.count(Project.id)).where(*conditions)
                ).scalar_one()
                or 0
            )
            rows = self._db.execute(statement).all()
            return (
                [
                    AdminProjectRow(
                        id=row[0],
                        user_id=row[1],
                        name=row[2],
                        repo_owner=row[3],
                        repo_name=row[4],
                        branch=row[5],
                        created_at=row[6],
                        updated_at=row[7],
                        owner_id=row[8],
                        owner_username=row[9],
                        owner_email=row[10],
                        scan_count=int(row[11] or 0),
                        average_scan_duration_seconds=(
                            round(float(row[12]), 2) if row[12] is not None else None
                        ),
                    )
                    for row in rows
                ],
                total,
            )
        except (KeyError, SQLAlchemyError) as exc:
            raise DatabaseOperationException(
                "Failed to list administrative projects",
                details={
                    "sort_by": filters.sort_by,
                    "sort_order": filters.sort_order,
                    "query": filters.query,
                },
            ) from exc
