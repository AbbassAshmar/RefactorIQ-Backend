from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

logger = logging.getLogger(__name__)


class CodeEmbeddingProvider(Protocol):
    model_id: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode code snippets into dense vectors."""


class CodeEmbeddingService:
    """Lazy Transformers adapter for code embedding models."""

    DEFAULT_MODEL_ID = "Salesforce/SFR-Embedding-Code-400M_R"

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        batch_size: int = 8,
        device: str | None = None,
        max_length: int = 8192,
        trust_remote_code: bool = True,
    ) -> None:
        self.model_id = model_id
        self.batch_size = batch_size
        self.device = device
        self.max_length = max_length
        self.trust_remote_code = trust_remote_code
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._functional = None

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        prepared = [text if text.strip() else " " for text in texts]
        if not prepared:
            return []

        self._ensure_loaded()

        vectors: list[list[float]] = []
        for start in range(0, len(prepared), self.batch_size):
            batch = prepared[start : start + self.batch_size]
            encoded = self._tokenizer(
                batch,
                max_length=self.max_length,
                padding=True,
                truncation=True,
                return_tensors="pt",
            )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}

            with self._torch.no_grad():
                outputs = self._model(**encoded)
                hidden_states = self._last_hidden_state(outputs)
                pooled = hidden_states[:, 0]
                pooled = self._functional.normalize(pooled, p=2, dim=1)

            vectors.extend(pooled.detach().cpu().float().tolist())

        return [[float(value) for value in vector] for vector in vectors]

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        self._apply_transformers_compatibility_patches()

        try:
            import torch
            import torch.nn.functional as functional
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Semantic duplication analysis requires torch and transformers"
            ) from exc

        self.device = self._select_device(self.device)
        logger.info("[EMBEDDINGS] loading code embedding model %s on %s", self.model_id, self.device)
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            trust_remote_code=self.trust_remote_code,
        )
        if getattr(tokenizer, "pad_token", None) is None and getattr(tokenizer, "eos_token", None) is not None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModel.from_pretrained(
            self.model_id,
            trust_remote_code=self.trust_remote_code,
        )
        model.to(self.device)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch
        self._functional = functional

    def _last_hidden_state(self, outputs: object) -> object:
        hidden_states = getattr(outputs, "last_hidden_state", None)
        if hidden_states is not None:
            return hidden_states

        if isinstance(outputs, (tuple, list)) and outputs:
            return outputs[0]

        raise RuntimeError(f"Model {self.model_id} did not return last_hidden_state")

    def _select_device(self, requested: str | None) -> str:
        if requested:
            return requested

        try:
            import torch
        except Exception:
            return "cpu"

        if torch.cuda.is_available():
            return "cuda"

        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return "mps"

        return "cpu"

    def _apply_transformers_compatibility_patches(self) -> None:
        try:
            import transformers.modeling_utils as modeling_utils
        except Exception:
            return

        if hasattr(modeling_utils, "Conv1D"):
            return

        try:
            from transformers.pytorch_utils import Conv1D
        except Exception:
            return

        modeling_utils.Conv1D = Conv1D
