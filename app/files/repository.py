from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.enums import ScanStatus
from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.files.dtos import CircularDependencyRow, FileDetailRow, FileListRow, FileRelationshipRow
from app.models import (
    CircularDependencyGroup,
    CircularDependencyMember,
    CoChangeEdge,
    DependencyEdge,
    Project,
    Scan,
    ScanFile,
)


class FileRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

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
            grouped: dict[uuid.UUID, list[FileListRow]] = defaultdict(list)
            sizes: dict[uuid.UUID, int] = {}
            for group_id, size, member_id, file_path, priority_band in rows:
                sizes[group_id] = size
                grouped[group_id].append(FileListRow(member_id, file_path, priority_band))
            return [CircularDependencyRow(group_id, sizes[group_id], members) for group_id, members in grouped.items()]
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
        try:
            statement = (
                select(Scan.id)
                .join(Project, Scan.project_id == Project.id)
                .where(Scan.id == scan_id, Project.user_id == user_id, Scan.status == ScanStatus.SUCCEEDED)
            )
            if self._db.execute(statement).scalar_one_or_none() is None:
                raise RecordNotFoundException("Successful scan not found", details={"scan_id": str(scan_id)})
        except RecordNotFoundException:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseOperationException("Failed to validate scan access", details={"scan_id": str(scan_id)}) from exc

    def _files_by_ids(self, file_ids: set[uuid.UUID]) -> dict[uuid.UUID, ScanFile]:
        if not file_ids:
            return {}
        files = self._db.execute(select(ScanFile).where(ScanFile.id.in_(file_ids))).scalars().all()
        return {file.id: file for file in files}

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
