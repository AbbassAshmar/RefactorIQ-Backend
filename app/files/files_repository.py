from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from app.core.enums import ScanStatus
from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.files.files_dtos import (
    CircularDependencyRow,
    DependencyEdgeRow,
    FileDetailRow,
    FileListRow,
    FileRelationshipRow,
    FilesAnalyzedRow,
    PriorityDistributionRow,
)
from app.models import (
    CircularDependencyGroup,
    CircularDependencyMember,
    CoChangeEdge,
    DependencyEdge,
    Project,
    Scan,
    ScanFile,
)


logger = logging.getLogger(__name__)


class FileRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def project_belongs_to_user(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        try:
            statement = select(func.count(Project.id)).where(
                Project.id == project_id,
                Project.user_id == user_id,
            )
            return bool(self._db.execute(statement).scalar_one())
        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to validate file analytics project access user_id=%s project_id=%s",
                user_id,
                project_id,
            )
            raise DatabaseOperationException(
                "Failed to validate project access",
                details={"project_id": str(project_id)},
            ) from exc

    def list_project_priority_distribution(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        limit: int,
    ) -> list[PriorityDistributionRow]:
        try:
            latest_scans = (
                select(Scan.id, Scan.finished_at)
                .join(Project, Scan.project_id == Project.id)
                .where(
                    Project.id == project_id,
                    Project.user_id == user_id,
                    Scan.status == ScanStatus.SUCCEEDED,
                    Scan.finished_at.is_not(None),
                )
                .order_by(Scan.finished_at.desc(), Scan.id.desc())
                .limit(limit)
                .subquery()
            )
            statement = (
                select(
                    latest_scans.c.id,
                    latest_scans.c.finished_at,
                    ScanFile.priority_band,
                    func.count(ScanFile.id),
                )
                .select_from(latest_scans)
                .outerjoin(ScanFile, ScanFile.scan_id == latest_scans.c.id)
                .group_by(
                    latest_scans.c.id,
                    latest_scans.c.finished_at,
                    ScanFile.priority_band,
                )
                .order_by(latest_scans.c.finished_at.asc(), latest_scans.c.id.asc())
            )
            grouped: dict[uuid.UUID, tuple[object, dict[str, int]]] = {}
            for scan_id, finished_at, priority_band, count in self._db.execute(statement).all():
                timestamp, counts = grouped.setdefault(scan_id, (finished_at, {}))
                band = str(priority_band).lower() if priority_band is not None else "unknown"
                counts[band] = int(count)
            return [
                PriorityDistributionRow(scan_id, timestamp, counts)
                for scan_id, (timestamp, counts) in grouped.items()
            ]
        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to build project priority distribution user_id=%s project_id=%s",
                user_id,
                project_id,
            )
            raise DatabaseOperationException(
                "Failed to build project priority distribution",
                details={"project_id": str(project_id)},
            ) from exc

    def list_project_file_counts(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        limit: int,
    ) -> list[FilesAnalyzedRow]:
        try:
            latest_scans = (
                select(Scan.id, Scan.finished_at)
                .join(Project, Scan.project_id == Project.id)
                .where(
                    Project.id == project_id,
                    Project.user_id == user_id,
                    Scan.status == ScanStatus.SUCCEEDED,
                    Scan.finished_at.is_not(None),
                )
                .order_by(Scan.finished_at.desc(), Scan.id.desc())
                .limit(limit)
                .subquery()
            )
            statement = (
                select(
                    latest_scans.c.id,
                    latest_scans.c.finished_at,
                    func.count(ScanFile.id),
                )
                .select_from(latest_scans)
                .outerjoin(ScanFile, ScanFile.scan_id == latest_scans.c.id)
                .group_by(latest_scans.c.id, latest_scans.c.finished_at)
                .order_by(latest_scans.c.finished_at.asc(), latest_scans.c.id.asc())
            )
            return [
                FilesAnalyzedRow(scan_id, finished_at, int(file_count))
                for scan_id, finished_at, file_count in self._db.execute(statement).all()
            ]
        except SQLAlchemyError as exc:
            logger.exception(
                "Failed to build project file count trend user_id=%s project_id=%s",
                user_id,
                project_id,
            )
            raise DatabaseOperationException(
                "Failed to build project file count trend",
                details={"project_id": str(project_id)},
            ) from exc

    def list_by_scan(self, user_id: uuid.UUID, scan_id: uuid.UUID) -> list[FileListRow]:
        self._ensure_scan_access(user_id, scan_id)
        try:
            statement = (
                select(ScanFile.id, ScanFile.file_path, ScanFile.priority_band)
                .where(ScanFile.scan_id == scan_id)
                .order_by(ScanFile.file_path.asc())
            )
            return [FileListRow(id=row[0], file_path=row[1], priority_band=row[2]) for row in self._db.execute(statement).all()]
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to list scan files", details={"scan_id": str(scan_id)}) from exc

    def get_details(self, user_id: uuid.UUID, file_id: uuid.UUID) -> FileDetailRow:
        try:
            statement = (
                select(ScanFile, Scan.finished_at)
                .join(Scan, ScanFile.scan_id == Scan.id)
                .join(Project, Scan.project_id == Project.id)
                .where(
                    ScanFile.id == file_id,
                    Project.user_id == user_id,
                    Scan.status == ScanStatus.SUCCEEDED,
                )
            )
            row = self._db.execute(statement).one_or_none()
            if row is None:
                raise RecordNotFoundException("File not found", details={"file_id": str(file_id)})
            file, scan_finished_at = row
            return self._to_detail_row(file, scan_finished_at)
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to load file details", details={"file_id": str(file_id)}) from exc

    def list_scan_dependency_graph(
        self,
        user_id: uuid.UUID,
        scan_id: uuid.UUID,
    ) -> tuple[list[FileListRow], list[DependencyEdgeRow]]:
        started_at = time.perf_counter()
        logger.debug("Loading dependency graph rows user_id=%s scan_id=%s", user_id, scan_id)
        self._ensure_scan_access(user_id, scan_id)
        try:
            node_rows = self._db.execute(
                select(ScanFile.id, ScanFile.file_path, ScanFile.priority_band)
                .where(ScanFile.scan_id == scan_id)
                .order_by(ScanFile.file_path.asc())
            ).all()

            source_file = aliased(ScanFile)
            target_file = aliased(ScanFile)
            edge_rows = self._db.execute(
                select(DependencyEdge.source_file_id, DependencyEdge.target_file_id)
                .join(source_file, source_file.id == DependencyEdge.source_file_id)
                .join(target_file, target_file.id == DependencyEdge.target_file_id)
                .where(DependencyEdge.scan_id == scan_id)
                .order_by(source_file.file_path.asc(), target_file.file_path.asc())
            ).all()

            nodes = [FileListRow(row[0], row[1], row[2]) for row in node_rows]
            edges = [DependencyEdgeRow(row[0], row[1]) for row in edge_rows]
            logger.info(
                "Loaded dependency graph rows user_id=%s scan_id=%s nodes=%d edges=%d duration_ms=%.2f",
                user_id,
                scan_id,
                len(nodes),
                len(edges),
                (time.perf_counter() - started_at) * 1000,
            )
            return nodes, edges
        except SQLAlchemyError as exc:
            logger.exception(
                "Database error loading dependency graph user_id=%s scan_id=%s",
                user_id,
                scan_id,
            )
            raise DatabaseOperationException(
                "Failed to load scan dependency graph",
                details={"scan_id": str(scan_id)},
            ) from exc

    def list_scan_circular_dependencies(
        self,
        user_id: uuid.UUID,
        scan_id: uuid.UUID,
    ) -> list[CircularDependencyRow]:
        started_at = time.perf_counter()
        logger.debug("Loading circular dependency rows user_id=%s scan_id=%s", user_id, scan_id)
        self._ensure_scan_access(user_id, scan_id)
        try:
            rows = self._db.execute(
                select(
                    CircularDependencyGroup.id,
                    CircularDependencyGroup.size,
                    ScanFile.id,
                    ScanFile.file_path,
                    ScanFile.priority_band,
                )
                .join(CircularDependencyMember, CircularDependencyMember.group_id == CircularDependencyGroup.id)
                .join(ScanFile, ScanFile.id == CircularDependencyMember.file_id)
                .where(CircularDependencyGroup.scan_id == scan_id)
                .order_by(CircularDependencyGroup.id.asc(), ScanFile.file_path.asc())
            ).all()
            groups = self._group_circular_dependency_rows(rows)
            logger.info(
                "Loaded circular dependency rows user_id=%s scan_id=%s groups=%d members=%d duration_ms=%.2f",
                user_id,
                scan_id,
                len(groups),
                sum(len(group.members) for group in groups),
                (time.perf_counter() - started_at) * 1000,
            )
            return groups
        except SQLAlchemyError as exc:
            logger.exception(
                "Database error loading circular dependencies user_id=%s scan_id=%s",
                user_id,
                scan_id,
            )
            raise DatabaseOperationException(
                "Failed to load scan circular dependencies",
                details={"scan_id": str(scan_id)},
            ) from exc

    def list_dependencies(self, scan_id: uuid.UUID, file_id: uuid.UUID) -> list[FileRelationshipRow]:
        try:
            edge_statement = select(DependencyEdge).where(
                DependencyEdge.scan_id == scan_id,
                or_(DependencyEdge.source_file_id == file_id, DependencyEdge.target_file_id == file_id),
            )
            edges = self._db.execute(edge_statement).scalars().all()
            related_ids = {
                edge.target_file_id if edge.source_file_id == file_id else edge.source_file_id
                for edge in edges
            }
            files = self._files_by_ids(related_ids)
            relationships = []
            for edge in edges:
                outgoing = edge.source_file_id == file_id
                related_id = edge.target_file_id if outgoing else edge.source_file_id
                related = files.get(related_id)
                if related is None:
                    continue
                relationships.append(self._to_relationship_row(related, "dependency", "outgoing" if outgoing else "incoming"))
            return relationships
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to load file dependencies", details={"file_id": str(file_id)}) from exc

    def list_co_changed_files(self, scan_id: uuid.UUID, file_id: uuid.UUID) -> list[FileRelationshipRow]:
        try:
            statement = select(CoChangeEdge).where(
                CoChangeEdge.scan_id == scan_id,
                or_(CoChangeEdge.file_id_a == file_id, CoChangeEdge.file_id_b == file_id),
            )
            edges = self._db.execute(statement).scalars().all()
            related_ids = {
                edge.file_id_b if edge.file_id_a == file_id else edge.file_id_a
                for edge in edges
            }
            files = self._files_by_ids(related_ids)
            return [self._to_relationship_row(files[file_id], "co_change") for file_id in related_ids if file_id in files]
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to load co-changed files", details={"file_id": str(file_id)}) from exc

    def list_circular_dependencies(self, scan_id: uuid.UUID, file_id: uuid.UUID) -> list[CircularDependencyRow]:
        try:
            group_ids = self._db.execute(
                select(CircularDependencyMember.group_id).where(CircularDependencyMember.file_id == file_id)
            ).scalars().all()
            if not group_ids:
                return []
            rows = self._db.execute(
                select(
                    CircularDependencyGroup.id,
                    CircularDependencyGroup.size,
                    ScanFile.id,
                    ScanFile.file_path,
                    ScanFile.priority_band,
                )
                .join(CircularDependencyMember, CircularDependencyMember.group_id == CircularDependencyGroup.id)
                .join(ScanFile, ScanFile.id == CircularDependencyMember.file_id)
                .where(CircularDependencyGroup.scan_id == scan_id, CircularDependencyGroup.id.in_(group_ids))
                .order_by(CircularDependencyGroup.id.asc(), ScanFile.file_path.asc())
            ).all()
            return self._group_circular_dependency_rows(rows)
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to load circular dependencies", details={"file_id": str(file_id)}) from exc

    def references_by_paths(self, scan_id: uuid.UUID, file_paths: set[str]) -> dict[str, FileListRow]:
        if not file_paths:
            return {}
        try:
            rows = self._db.execute(
                select(ScanFile.id, ScanFile.file_path, ScanFile.priority_band).where(
                    ScanFile.scan_id == scan_id,
                    ScanFile.file_path.in_(file_paths),
                )
            ).all()
            return {row[1]: FileListRow(row[0], row[1], row[2]) for row in rows}
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to resolve related files", details={"scan_id": str(scan_id)}) from exc

    def _ensure_scan_access(self, user_id: uuid.UUID, scan_id: uuid.UUID) -> None:
        logger.debug("Validating successful scan access user_id=%s scan_id=%s", user_id, scan_id)
        try:
            statement = (
                select(Scan.id)
                .join(Project, Scan.project_id == Project.id)
                .where(Scan.id == scan_id, Project.user_id == user_id, Scan.status == ScanStatus.SUCCEEDED)
            )
            if self._db.execute(statement).scalar_one_or_none() is None:
                logger.warning("Successful scan access denied user_id=%s scan_id=%s", user_id, scan_id)
                raise RecordNotFoundException("Successful scan not found", details={"scan_id": str(scan_id)})
            logger.debug("Successful scan access validated user_id=%s scan_id=%s", user_id, scan_id)
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            logger.exception("Database error validating scan access user_id=%s scan_id=%s", user_id, scan_id)
            raise DatabaseOperationException("Failed to validate scan access", details={"scan_id": str(scan_id)}) from exc

    def _files_by_ids(self, file_ids: set[uuid.UUID]) -> dict[uuid.UUID, ScanFile]:
        if not file_ids:
            return {}
        files = self._db.execute(select(ScanFile).where(ScanFile.id.in_(file_ids))).scalars().all()
        return {file.id: file for file in files}

    def _group_circular_dependency_rows(self, rows) -> list[CircularDependencyRow]:
        grouped: dict[uuid.UUID, list[FileListRow]] = defaultdict(list)
        sizes: dict[uuid.UUID, int] = {}
        for group_id, size, member_id, file_path, priority_band in rows:
            sizes[group_id] = size
            grouped[group_id].append(FileListRow(member_id, file_path, priority_band))

        groups = [
            CircularDependencyRow(group_id, sizes[group_id], members)
            for group_id, members in grouped.items()
        ]
        return sorted(groups, key=lambda group: tuple(member.file_path for member in group.members))

    def _to_detail_row(self, file: ScanFile, scan_finished_at) -> FileDetailRow:
        return FileDetailRow(
            id=file.id,
            scan_id=file.scan_id,
            file_path=file.file_path,
            refactor_score=float(file.refactor_score) if file.refactor_score is not None else None,
            priority_band=file.priority_band,
            metrics=file.metrics or {},
            metadata=file.metadata_json or {},
            errors=file.errors or {},
            created_at=file.created_at,
            scan_finished_at=scan_finished_at,
        )

    def _to_relationship_row(self, file: ScanFile, relationship: str, direction: str | None = None) -> FileRelationshipRow:
        return FileRelationshipRow(
            id=file.id,
            file_path=file.file_path,
            priority_band=file.priority_band,
            metrics=file.metrics or {},
            relationship=relationship,
            direction=direction,
        )
