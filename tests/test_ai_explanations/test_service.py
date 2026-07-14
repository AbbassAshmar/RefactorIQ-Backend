from __future__ import annotations

import uuid

from app.ai_explanations.ai_explanations_dtos import AiExplanationRow, AiExplanationType
from app.ai_explanations.ai_explanations_service import AiExplanationService


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return f"generated: {prompt}"


class FakeRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[uuid.UUID, str], AiExplanationRow] = {}

    def get_for_file(self, file_id, explanation_type):
        return self.rows.get((file_id, explanation_type.value))

    def create_for_file(self, file_id, explanation_type, explanation):
        row = AiExplanationRow(
            id=uuid.uuid4(),
            type=explanation_type.value,
            explanation=explanation,
            file_id=file_id,
        )
        self.rows[(file_id, explanation_type.value)] = row
        return row


def test_file_explanation_is_generated_once_and_then_cached():
    repository = FakeRepository()
    provider = FakeProvider()
    service = AiExplanationService(repository, provider)
    file_id = uuid.uuid4()

    first = service.get_or_generate_for_file(
        file_id,
        AiExplanationType.SUMMARY,
        "summarize this file",
    )
    second = service.get_or_generate_for_file(
        file_id,
        AiExplanationType.SUMMARY,
        "summarize this file",
    )

    assert first == second
    assert provider.calls == 1
