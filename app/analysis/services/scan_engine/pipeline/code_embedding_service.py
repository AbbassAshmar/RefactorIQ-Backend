from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
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
        model_path: str | Path | None = None,
        batch_size: int = 8,
        device: str | None = None,
        max_length: int = 8192,
        trust_remote_code: bool = True,
        local_files_only: bool = False,
    ) -> None:
        self.model_id = model_id
        self.model_path = Path(model_path).expanduser().resolve() if model_path else None
        self.batch_size = batch_size
        self.device = device
        self.max_length = max_length
        self.trust_remote_code = trust_remote_code
        self.local_files_only = local_files_only
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
            encoded.setdefault("position_ids", self._position_ids_like(encoded["input_ids"]))

            with self._torch.no_grad():
                outputs = self._model(**encoded)
                hidden_states = self._last_hidden_state(outputs)
                pooled = hidden_states[:, 0]
                pooled = self._torch.nan_to_num(pooled, nan=0.0, posinf=0.0, neginf=0.0)
                pooled = self._functional.normalize(pooled, p=2, dim=1)
                pooled = self._torch.nan_to_num(pooled, nan=0.0, posinf=0.0, neginf=0.0)

            vectors.extend(pooled.detach().cpu().float().tolist())

        return [[float(value) for value in vector] for vector in vectors]

    def _position_ids_like(self, input_ids: object) -> object:
        seq_length = input_ids.shape[1]
        return self._torch.arange(
            seq_length,
            device=input_ids.device,
            dtype=input_ids.dtype,
        ).unsqueeze(0).expand(input_ids.shape[0], -1)

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
        model_source = self._model_source()
        logger.info("[EMBEDDINGS] loading code embedding model from %s on %s", model_source, self.device)
        tokenizer = AutoTokenizer.from_pretrained(
            model_source,
            trust_remote_code=self.trust_remote_code,
            local_files_only=self.local_files_only,
        )
        if getattr(tokenizer, "pad_token", None) is None and getattr(tokenizer, "eos_token", None) is not None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModel.from_pretrained(
            model_source,
            trust_remote_code=self.trust_remote_code,
            local_files_only=self.local_files_only,
        )
        model.to(self.device)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch
        self._functional = functional

    def _model_source(self) -> str:
        if self.model_path is None:
            return self.model_id

        if not self.model_path.exists():
            raise RuntimeError(f"Local embedding model path does not exist: {self.model_path}")

        if not (self.model_path / "config.json").exists():
            raise RuntimeError(
                f"Local embedding model path must contain config.json: {self.model_path}"
            )

        return str(self.model_path)

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
