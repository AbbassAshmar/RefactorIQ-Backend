from __future__ import annotations

import json
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


def test_jina_embedding_service_passes_zero_token_type_ids() -> None:
    service = CodeEmbeddingService(batch_size=2)
    model = RecordingModel()
    service._tokenizer = FakeTokenizer()
    service._model = model
    service._torch = torch
    service._functional = functional
    service.device = "cpu"

    service.encode(["alpha", "beta"])

    assert torch.equal(model.token_type_ids, torch.zeros(2, 3, dtype=torch.long))


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


def test_codesage_pooling_uses_attention_mask_and_model_limit() -> None:
    service = CodeEmbeddingService(
        model_id="codesage/codesage-base-v2",
        max_length=8192,
    )
    service._tokenizer = SimpleNamespace(model_max_length=4096)
    service._model = SimpleNamespace(
        config=SimpleNamespace(max_position_embeddings=2048),
    )

    hidden_states = torch.tensor(
        [
            [[1.0, 0.0], [0.0, 1.0], [9.0, 9.0]],
        ]
    )
    attention_mask = torch.tensor([[1, 1, 0]])
    pooled = service._pool_hidden_states(
        SimpleNamespace(pooler_output=None),
        hidden_states,
        {"attention_mask": attention_mask},
    )

    assert torch.allclose(pooled, torch.tensor([[0.5, 0.5]]))
    assert service._effective_max_length() == 2048


def test_local_sentence_transformer_metadata_controls_pooling_and_limit(
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model"
    pooling_path = model_path / "1_Pooling"
    pooling_path.mkdir(parents=True)
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "sentence_bert_config.json").write_text(
        json.dumps({"max_seq_length": 768}),
        encoding="utf-8",
    )
    (pooling_path / "config.json").write_text(
        json.dumps(
            {
                "pooling_mode_cls_token": False,
                "pooling_mode_mean_tokens": True,
                "pooling_mode_max_tokens": False,
                "pooling_mode_mean_sqrt_len_tokens": False,
            }
        ),
        encoding="utf-8",
    )
    service = CodeEmbeddingService(
        model_id="example/model",
        model_path=model_path,
        max_length=1024,
    )

    service._load_sentence_transformer_metadata()

    assert service.pooling_mode == "mean"
    assert service._effective_max_length() == 768


def test_code_embedding_service_restores_order_after_length_bucketing() -> None:
    service = CodeEmbeddingService(
        model_id="example/model",
        batch_size=2,
        pooling_mode="cls",
    )
    service._tokenizer = LengthTokenizer()
    service._model = LengthEchoModel()
    service._torch = torch
    service._functional = functional
    service.device = "cpu"

    vectors = service.encode(["longest", "x", "medium"])

    expected_first_values = [
        length / math.sqrt(length * length + 1)
        for length in (7, 1, 6)
    ]
    assert [vector[0] for vector in vectors] == pytest.approx(expected_first_values)


def test_legacy_model_compatibility_head_mask_fallback() -> None:
    service = CodeEmbeddingService(model_id="codesage/codesage-base-v2")
    pretrained_model = type("PreTrainedModel", (), {})

    service._patch_legacy_head_mask(pretrained_model)

    model = SimpleNamespace(dtype=torch.float32)
    assert pretrained_model.get_head_mask(model, None, 2) == [None, None]

    head_mask = pretrained_model.get_head_mask(model, torch.ones(2), 3)
    assert head_mask.shape == (3, 1, 2, 1, 1)


def test_legacy_jina_config_receives_encoder_defaults() -> None:
    service = CodeEmbeddingService()
    model_config = SimpleNamespace()

    service._apply_model_config_compatibility(model_config)

    assert model_config.is_decoder is False
    assert model_config.add_cross_attention is False
    assert model_config.chunk_size_feed_forward == 0


class FakeTokenizer:
    def __call__(self, batch, **_: object) -> dict[str, torch.Tensor]:
        return {
            "input_ids": torch.tensor([[101, 102, 0], [101, 103, 104]]),
            "attention_mask": torch.tensor([[1, 1, 0], [1, 1, 1]]),
        }


class RecordingModel:
    def __init__(self) -> None:
        self.position_ids: torch.Tensor | None = None
        self.token_type_ids: torch.Tensor | None = None

    def __call__(self, **encoded: torch.Tensor) -> SimpleNamespace:
        self.position_ids = encoded["position_ids"].detach().cpu()
        if "token_type_ids" in encoded:
            self.token_type_ids = encoded["token_type_ids"].detach().cpu()
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


class LengthTokenizer:
    def __call__(self, batch: list[str], **_: object) -> dict[str, torch.Tensor]:
        return {
            "input_ids": torch.tensor([[len(text)] for text in batch]),
            "attention_mask": torch.ones(len(batch), 1, dtype=torch.long),
        }


class LengthEchoModel:
    def __call__(self, **encoded: torch.Tensor) -> SimpleNamespace:
        lengths = encoded["input_ids"].float().unsqueeze(-1)
        ones = torch.ones_like(lengths)
        return SimpleNamespace(last_hidden_state=torch.cat((lengths, ones), dim=-1))
