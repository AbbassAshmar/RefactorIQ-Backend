from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import PurePosixPath
from typing import Any

from app.ai_explanations.ai_explanations_dtos import AiExplanationType
from app.ai_explanations.ai_explanations_service import AiExplanationService
from app.core.constants import (
    ARCHITECTURAL_SUMMARY_PROMPT,
    GENERAL_SUMMARY_PROMPT,
    LANGUAGE_BY_EXTENSION,
    SCAN_DASHBOARD_HISTORY_LIMIT,
)
from app.core.exceptions.domain_exceptions import EntityNotFoundError, ExternalDependencyError, PersistenceError
from app.core.exceptions.repository_exceptions import DatabaseOperationException, RecordNotFoundException
from app.files.files_dtos import (
    CircularDependency,
    DependencyEdgeReference,
    DependencyGraphResponse,
    DuplicateMatch,
    FileDetailRow,
    FileDetailsResponse,
    FileListRow,
    FileListItem,
    FileListResponse,
    FileReference,
    FileRelationship,
    FileRelationshipRow,
    FileSummaries,
    ScanCircularDependenciesResponse,
    FilesAnalyzedPoint,
    FilesAnalyzedTrendResponse,
    PriorityBandCounts,
    PriorityDistributionTrendResponse,
    ScanPriorityDistributionPoint,
)
from app.files.files_repository import FileRepository
from app.utils.llm_provider import LlmProvider


logger = logging.getLogger(__name__)


class FileService:
    def __init__(
        self,
        repository: FileRepository,
        summary_provider: LlmProvider | None = None,
        ai_explanation_service: AiExplanationService | None = None,
    ) -> None:
        self._repository = repository
        self._summary_provider = summary_provider
        self._ai_explanation_service = ai_explanation_service

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

    def get_project_priority_distribution(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> PriorityDistributionTrendResponse:
        self._ensure_project_access(user_id=user_id, project_id=project_id)
        try:
            rows = self._repository.list_project_priority_distribution(
                user_id=user_id,
                project_id=project_id,
                limit=SCAN_DASHBOARD_HISTORY_LIMIT,
            )
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to load project priority distribution") from exc

        return PriorityDistributionTrendResponse(
            series=[
                ScanPriorityDistributionPoint(
                    scan_id=row.scan_id,
                    finished_at=row.finished_at,
                    priority_counts=PriorityBandCounts(
                        critical=row.counts.get("critical", 0),
                        high=row.counts.get("high", 0),
                        medium=row.counts.get("medium", 0),
                        low=row.counts.get("low", 0),
                    ),
                )
                for row in rows
            ]
        )

    def get_project_files_analyzed(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> FilesAnalyzedTrendResponse:
        self._ensure_project_access(user_id=user_id, project_id=project_id)
        try:
            rows = self._repository.list_project_file_counts(
                user_id=user_id,
                project_id=project_id,
                limit=SCAN_DASHBOARD_HISTORY_LIMIT,
            )
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to load project files analyzed trend") from exc

        return FilesAnalyzedTrendResponse(
            series=[
                FilesAnalyzedPoint(
                    scan_id=row.scan_id,
                    finished_at=row.finished_at,
                    files_analyzed=row.file_count,
                )
                for row in rows
            ]
        )

    def _ensure_project_access(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        try:
            owns_project = self._repository.project_belongs_to_user(
                project_id=project_id,
                user_id=user_id,
            )
        except DatabaseOperationException as exc:
            raise PersistenceError("Unable to validate project access") from exc
        if not owns_project:
            raise EntityNotFoundError("project", project_id)

    def list_scan_dependencies(
        self,
        user_id: uuid.UUID,
        scan_id: uuid.UUID,
    ) -> DependencyGraphResponse:
        started_at = time.perf_counter()
        logger.info("Building dependency graph user_id=%s scan_id=%s", user_id, scan_id)
        try:
            nodes, edges = self._repository.list_scan_dependency_graph(user_id, scan_id)
            logger.debug(
                "Dependency graph repository data loaded user_id=%s scan_id=%s nodes=%d edges=%d",
                user_id,
                scan_id,
                len(nodes),
                len(edges),
            )
            response = DependencyGraphResponse(
                scan_id=scan_id,
                nodes=[self._reference_schema(node) for node in nodes],
                edges=[
                    DependencyEdgeReference(
                        source_file_id=edge.source_file_id,
                        target_file_id=edge.target_file_id,
                    )
                    for edge in edges
                ],
            )
            logger.info(
                "Built dependency graph user_id=%s scan_id=%s nodes=%d edges=%d duration_ms=%.2f",
                user_id,
                scan_id,
                len(response.nodes),
                len(response.edges),
                (time.perf_counter() - started_at) * 1000,
            )
            return response
        except RecordNotFoundException as exc:
            logger.warning(
                "Dependency graph scan unavailable user_id=%s scan_id=%s reason=%s",
                user_id,
                scan_id,
                exc,
            )
            raise EntityNotFoundError("successful scan", scan_id) from exc
        except DatabaseOperationException as exc:
            logger.error(
                "Dependency graph persistence operation failed user_id=%s scan_id=%s reason=%s",
                user_id,
                scan_id,
                exc,
            )
            raise PersistenceError("Unable to load scan dependencies") from exc

    def list_scan_circular_dependencies(
        self,
        user_id: uuid.UUID,
        scan_id: uuid.UUID,
    ) -> ScanCircularDependenciesResponse:
        started_at = time.perf_counter()
        logger.info("Building circular dependencies response user_id=%s scan_id=%s", user_id, scan_id)
        try:
            groups = self._repository.list_scan_circular_dependencies(user_id, scan_id)
            logger.debug(
                "Circular dependency repository data loaded user_id=%s scan_id=%s groups=%d",
                user_id,
                scan_id,
                len(groups),
            )
            response = ScanCircularDependenciesResponse(
                scan_id=scan_id,
                circular_dependencies=[
                    CircularDependency(
                        group_id=group.group_id,
                        size=group.size,
                        members=[self._reference_schema(member) for member in group.members],
                    )
                    for group in groups
                ],
            )
            logger.info(
                "Built circular dependencies response user_id=%s scan_id=%s groups=%d duration_ms=%.2f",
                user_id,
                scan_id,
                len(response.circular_dependencies),
                (time.perf_counter() - started_at) * 1000,
            )
            return response
        except RecordNotFoundException as exc:
            logger.warning(
                "Circular dependencies scan unavailable user_id=%s scan_id=%s reason=%s",
                user_id,
                scan_id,
                exc,
            )
            raise EntityNotFoundError("successful scan", scan_id) from exc
        except DatabaseOperationException as exc:
            logger.error(
                "Circular dependencies persistence operation failed user_id=%s scan_id=%s reason=%s",
                user_id,
                scan_id,
                exc,
            )
            raise PersistenceError("Unable to load scan circular dependencies") from exc

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
            general_prompt = GENERAL_SUMMARY_PROMPT.format(context=context)
            general = (
                self._ai_explanation_service.get_or_generate_for_file(
                    file.id,
                    AiExplanationType.SUMMARY,
                    general_prompt,
                )
                if self._ai_explanation_service is not None
                else self._summary_provider.generate(general_prompt)
            )
        except ExternalDependencyError as exc:
            errors.append(str(exc))
        try:
            architecture_prompt = ARCHITECTURAL_SUMMARY_PROMPT.format(context=context)
            architectural = (
                self._ai_explanation_service.get_or_generate_for_file(
                    file.id,
                    AiExplanationType.ARCHITECTURE_SUMMARY,
                    architecture_prompt,
                )
                if self._ai_explanation_service is not None
                else self._summary_provider.generate(architecture_prompt)
            )
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
