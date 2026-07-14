from __future__ import annotations

import uuid
from collections.abc import Callable

from app.ai_explanations.ai_explanations_dtos import AiExplanationType
from app.ai_explanations.ai_explanations_repository import AiExplanationRepository
from app.core.exceptions.domain_exceptions import PersistenceError
from app.core.exceptions.repository_exceptions import DatabaseOperationException, DuplicateRecordException
from app.utils.llm_provider import LlmProvider


class AiExplanationService:
    def __init__(self, repository: AiExplanationRepository, provider: LlmProvider) -> None:
        self._repository = repository
        self._provider = provider

    def get_or_generate_for_file(
        self,
        file_id: uuid.UUID,
        explanation_type: AiExplanationType,
        prompt: str,
    ) -> str:
        return self._get_or_generate(
            explanation_type=explanation_type,
            prompt=prompt,
            get_cached=lambda: self._repository.get_for_file(file_id, explanation_type),
            save=lambda explanation: self._repository.create_for_file(
                file_id,
                explanation_type,
                explanation,
            ),
        )

    def get_or_generate_for_scan(
        self,
        scan_id: uuid.UUID,
        explanation_type: AiExplanationType,
        prompt: str,
    ) -> str:
        return self._get_or_generate(
            explanation_type=explanation_type,
            prompt=prompt,
            get_cached=lambda: self._repository.get_for_scan(scan_id, explanation_type),
            save=lambda explanation: self._repository.create_for_scan(
                scan_id,
                explanation_type,
                explanation,
            ),
        )

    def _get_or_generate(
        self,
        *,
        explanation_type: AiExplanationType,
        prompt: str,
        get_cached: Callable[[], object],
        save: Callable[[str], object],
    ) -> str:
        try:
            cached = get_cached()
            if cached is not None:
                return cached.explanation

            generated = self._provider.generate(prompt)
            return save(generated).explanation
        except (DatabaseOperationException, DuplicateRecordException) as exc:
            raise PersistenceError(
                f"Unable to load or store AI explanation: {explanation_type.value}"
            ) from exc
