from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
import torch.nn.functional as functional

from app.analysis.services.scan_engine.pipeline.code_embedding_service import (
    CodeEmbeddingService,
)


def test_code_embedding_service_uses_local_model_path(tmp_path: Path) -> None:
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "config.json").write_text("{}", encoding="utf-8")

    service = CodeEmbeddingService(
        model_id="example/model",
        model_path=model_path,
        local_files_only=True,
    )

    assert service._model_source() == str(model_path.resolve())


def test_code_embedding_service_falls_back_to_model_id() -> None:
    service = CodeEmbeddingService(model_id="example/model")

    assert service._model_source() == "example/model"


def test_code_embedding_service_rejects_invalid_local_model_path(tmp_path: Path) -> None:
    service = CodeEmbeddingService(model_path=tmp_path / "missing-model")

    with pytest.raises(RuntimeError, match="Local embedding model path does not exist"):
        service._model_source()


def test_code_embedding_service_passes_explicit_position_ids() -> None:
    service = CodeEmbeddingService(batch_size=2)
    model = RecordingModel()
    service._tokenizer = FakeTokenizer()
    service._model = model
    service._torch = torch
    service._functional = functional
    service.device = "cpu"

    vectors = service.encode(["alpha", "beta"])

    assert len(vectors) == 2
    assert torch.equal(model.position_ids, torch.tensor([[0, 1, 2], [0, 1, 2]]))


def test_code_embedding_service_sanitizes_non_finite_model_outputs() -> None:
    service = CodeEmbeddingService(batch_size=2)
    service._tokenizer = FakeTokenizer()
    service._model = NonFiniteModel()
    service._torch = torch
    service._functional = functional
    service.device = "cpu"

    vectors = service.encode(["alpha", "beta"])

    assert len(vectors) == 2
    assert all(math.isfinite(value) for vector in vectors for value in vector)


class FakeTokenizer:
    def __call__(self, batch, **_: object) -> dict[str, torch.Tensor]:
        return {
            "input_ids": torch.tensor([[101, 102, 0], [101, 103, 104]]),
            "attention_mask": torch.tensor([[1, 1, 0], [1, 1, 1]]),
        }


class RecordingModel:
    def __init__(self) -> None:
        self.position_ids: torch.Tensor | None = None

    def __call__(self, **encoded: torch.Tensor) -> SimpleNamespace:
        self.position_ids = encoded["position_ids"].detach().cpu()
        batch_size, seq_length = encoded["input_ids"].shape
        return SimpleNamespace(
            last_hidden_state=torch.ones(batch_size, seq_length, 4),
        )


class NonFiniteModel:
    def __call__(self, **encoded: torch.Tensor) -> SimpleNamespace:
        batch_size, seq_length = encoded["input_ids"].shape
        hidden = torch.ones(batch_size, seq_length, 4)
        hidden[0, 0, 0] = torch.nan
        hidden[1, 0, 1] = torch.inf
        return SimpleNamespace(last_hidden_state=hidden)
