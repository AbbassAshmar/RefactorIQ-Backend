from __future__ import annotations

import json
import uuid
from pathlib import PurePosixPath
from typing import Any

from app.core.exceptions.domain_exceptions import EntityNotFoundError, ExternalDependencyError, PersistenceError
from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.files.constants import LANGUAGE_BY_EXTENSION
from app.files.dtos import FileDetailRow, FileListRow, FileRelationshipRow
from app.files.prompts import ARCHITECTURAL_SUMMARY_PROMPT, GENERAL_SUMMARY_PROMPT
from app.files.repository import FileRepository
from app.files.schemas import (
    CircularDependency,
    DuplicateMatch,
    FileDetailsResponse,
    FileListItem,
    FileListResponse,
    FileReference,
    FileRelationship,
    FileSummaries,
)
from app.files.summary_provider import FileSummaryProvider


class FileService:
    def __init__(self, repository: FileRepository, summary_provider: FileSummaryProvider) -> None:
        self._repository = repository
        self._summary_provider = summary_provider

    def list_scan_files(self, user_id: uuid.UUID, scan_id: uuid.UUID) -> FileListResponse:
        try:
            files = self._repository.list_by_scan(user_id, scan_id)
            return FileListResponse(
                scan_id=scan_id,
                files=[FileListItem.model_validate(file, from_attributes=True) for file in files],
            )
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("successful scan", scan_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to list scan files") from exc

    def get_file_details(
        self,
        user_id: uuid.UUID,
        file_id: uuid.UUID,
        *,
        include_summary: bool = False,
    ) -> FileDetailsResponse:
        try:
            file = self._repository.get_details(user_id, file_id)
            dependencies = self._repository.list_dependencies(file.scan_id, file.id)
            co_changed_files = self._repository.list_co_changed_files(file.scan_id, file.id)
            circular_rows = self._repository.list_circular_dependencies(file.scan_id, file.id)
            duplicate_matches = self._duplicate_matches(file)
            summaries = self._summaries(
                file=file,
                dependencies=dependencies,
                circular_dependencies=circular_rows,
            ) if include_summary else None

            return FileDetailsResponse(
                id=file.id,
                scan_id=file.scan_id,
                file_path=file.file_path,
                language=self._language_for(file.file_path),
                refactor_score=file.refactor_score,
                priority_band=file.priority_band,
                created_at=file.created_at,
                last_scan_at=file.scan_finished_at,
                metrics=file.metrics,
                metadata=file.metadata,
                errors=file.errors,
                dependencies=[self._relationship_schema(item) for item in dependencies],
                co_changed_files=[self._relationship_schema(item) for item in co_changed_files],
                circular_dependencies=[
                    CircularDependency(
                        group_id=group.group_id,
                        size=group.size,
                        members=[self._reference_schema(member) for member in group.members],
                    )
                    for group in circular_rows
                ],
                duplicate_matches=duplicate_matches,
                summaries=summaries,
            )
        except RecordNotFoundException as exc:
            raise EntityNotFoundError("file", file_id) from exc
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to load file details") from exc

    def _duplicate_matches(self, file: FileDetailRow) -> list[DuplicateMatch]:
        metadata = file.metadata.get("duplication_analysis", {})
        if not isinstance(metadata, dict):
            return []

        raw_matches: list[tuple[str, dict[str, Any]]] = []
        for match_type, key in (
            ("syntax", "syntax_duplicate_blocks_sample"),
            ("semantic", "semantic_duplicate_blocks_sample"),
        ):
            for item in metadata.get(key, []) or []:
                if isinstance(item, dict):
                    raw_matches.append((match_type, item))

        file_paths = {
            str(path)
            for _, item in raw_matches
            for path in item.get("matched_files", [])
        }
        references = self._repository.references_by_paths(file.scan_id, file_paths)
        return [
            DuplicateMatch(
                match_type=match_type,
                kind=item.get("kind"),
                start_line=item.get("start_line"),
                end_line=item.get("end_line"),
                max_similarity=item.get("max_similarity"),
                matched_files=[
                    self._reference_schema(references[path])
                    for path in item.get("matched_files", [])
                    if path in references
                ],
            )
            for match_type, item in raw_matches
        ]

    def _summaries(
        self,
        *,
        file: FileDetailRow,
        dependencies: list[FileRelationshipRow],
        circular_dependencies,
    ) -> FileSummaries:
        context = json.dumps(
            {
                "file_path": file.file_path,
                "priority_band": file.priority_band,
                "refactor_score": file.refactor_score,
                "metrics": file.metrics,
                "metadata": file.metadata,
                "errors": file.errors,
                "dependencies": [
                    {
                        "file_path": dependency.file_path,
                        "direction": dependency.direction,
                        "metrics": dependency.metrics,
                    }
                    for dependency in dependencies
                ],
                "circular_dependencies": [
                    {
                        "size": group.size,
                        "members": [member.file_path for member in group.members],
                    }
                    for group in circular_dependencies
                ],
            },
            default=str,
            sort_keys=True,
        )

        general = None
        architectural = None
        errors = []
        try:
            general = self._summary_provider.generate(GENERAL_SUMMARY_PROMPT.format(context=context))
        except ExternalDependencyError as exc:
            errors.append(str(exc))
        try:
            architectural = self._summary_provider.generate(ARCHITECTURAL_SUMMARY_PROMPT.format(context=context))
        except ExternalDependencyError as exc:
            errors.append(str(exc))
        return FileSummaries(
            general=general,
            architectural=architectural,
            error="; ".join(dict.fromkeys(errors)) or None,
        )

    def _language_for(self, file_path: str) -> str:
        return LANGUAGE_BY_EXTENSION.get(PurePosixPath(file_path).suffix.lower(), "Unknown")

    def _reference_schema(self, file: FileListRow) -> FileReference:
        return FileReference(id=file.id, file_path=file.file_path, priority_band=file.priority_band)

    def _relationship_schema(self, file: FileRelationshipRow) -> FileRelationship:
        return FileRelationship(
            id=file.id,
            file_path=file.file_path,
            priority_band=file.priority_band,
            relationship=file.relationship,
            direction=file.direction,
            metrics=file.metrics,
        )
