from __future__ import annotations

import logging
from time import perf_counter
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
        started = perf_counter()
        prepared = [text if text.strip() else " " for text in texts]
        if not prepared:
            logger.debug("[EMBEDDINGS SKIPPED] text_count=0")
            return []

        logger.info(
            "[EMBEDDINGS ENCODE STARTED] model=%s text_count=%d batch_size=%d",
            self.model_id,
            len(prepared),
            self.batch_size,
        )
        try:
            self._ensure_loaded()
        except Exception:
            logger.exception("[EMBEDDINGS LOAD FAILED] model=%s", self.model_id)
            raise

        vectors: list[list[float]] = []
        for start in range(0, len(prepared), self.batch_size):
            batch = prepared[start : start + self.batch_size]
            batch_started = perf_counter()
            logger.debug(
                "[EMBEDDINGS BATCH STARTED] model=%s batch_start=%d batch_count=%d",
                self.model_id,
                start,
                len(batch),
            )
            try:
                encoded = self._tokenizer(
                    batch,
                    max_length=self._effective_max_length(),
                    padding=True,
                    truncation=True,
                    return_tensors="pt",
                )
                encoded = {key: value.to(self.device) for key, value in encoded.items()}
                encoded.setdefault("position_ids", self._position_ids_like(encoded["input_ids"]))

                with self._torch.no_grad():
                    outputs = self._model(**encoded)
                    hidden_states = self._last_hidden_state(outputs)
                    pooled = self._pool_hidden_states(outputs, hidden_states, encoded)
                    pooled = self._torch.nan_to_num(pooled, nan=0.0, posinf=0.0, neginf=0.0)
                    pooled = self._functional.normalize(pooled, p=2, dim=1)
                    pooled = self._torch.nan_to_num(pooled, nan=0.0, posinf=0.0, neginf=0.0)

                vectors.extend(pooled.detach().cpu().float().tolist())
            except Exception:
                logger.exception(
                    "[EMBEDDINGS BATCH FAILED] model=%s batch_start=%d batch_count=%d",
                    self.model_id,
                    start,
                    len(batch),
                )
                raise

            logger.debug(
                "[EMBEDDINGS BATCH COMPLETED] model=%s batch_start=%d batch_count=%d elapsed_seconds=%.3f",
                self.model_id,
                start,
                len(batch),
                perf_counter() - batch_started,
            )

        result = [[float(value) for value in vector] for vector in vectors]
        logger.info(
            "[EMBEDDINGS ENCODE COMPLETED] model=%s text_count=%d vector_count=%d dimension=%d elapsed_seconds=%.3f",
            self.model_id,
            len(prepared),
            len(result),
            len(result[0]) if result else 0,
            perf_counter() - started,
        )
        return result

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

        logger.debug("[EMBEDDINGS LOAD STARTED] model=%s", self.model_id)
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
        logger.info("[EMBEDDINGS MODEL CONFIGURED] model=%s device=%s", self.model_id, self.device)
        tokenizer_kwargs: dict[str, object] = {
            "trust_remote_code": self.trust_remote_code,
            "local_files_only": self.local_files_only,
        }
        if self._is_codesage_model():
            # CodeSage was trained with an EOS token appended to every sequence.
            tokenizer_kwargs["add_eos_token"] = True

        tokenizer = AutoTokenizer.from_pretrained(
            model_source,
            **tokenizer_kwargs,
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
        logger.info("[EMBEDDINGS LOADED] model=%s device=%s", self.model_id, self.device)

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

    def _pool_hidden_states(
        self,
        outputs: object,
        hidden_states: object,
        encoded: dict[str, object],
    ) -> object:
        if not self._is_codesage_model():
            return hidden_states[:, 0]

        # CodeSage exposes the same mean-pooled representation used by its
        # SentenceTransformers configuration. Prefer the model-provided value
        # when available, and retain a masked mean fallback for tuple outputs.
        pooled_output = getattr(outputs, "pooler_output", None)
        if pooled_output is not None:
            return pooled_output

        attention_mask = encoded.get("attention_mask")
        if attention_mask is None:
            return hidden_states.mean(dim=1)

        mask = attention_mask.unsqueeze(-1).to(dtype=hidden_states.dtype)
        return (hidden_states * mask).sum(dim=1) / mask.sum(dim=1).clamp_min(1.0)

    def _effective_max_length(self) -> int:
        limits = [self.max_length]
        for value in (
            getattr(getattr(self._model, "config", None), "max_position_embeddings", None),
            getattr(self._tokenizer, "model_max_length", None),
        ):
            if isinstance(value, int) and 0 < value < 1_000_000:
                limits.append(value)
        return min(limits)

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

    def _is_codesage_model(self) -> bool:
        model_source = f"{self.model_id} {self.model_path or ''}".lower()
        return "codesage" in model_source

    def _apply_transformers_compatibility_patches(self) -> None:
        try:
            import transformers
            import transformers.modeling_utils as modeling_utils
        except Exception:
            return

        if not hasattr(modeling_utils, "Conv1D"):
            try:
                from transformers.pytorch_utils import Conv1D
            except Exception:
                pass
            else:
                modeling_utils.Conv1D = Conv1D

        if self._is_codesage_model() and getattr(transformers, "__version__", "").startswith("5."):
            # CodeSage's remote model calls init_weights() directly and does
            # not run the Transformers 5 post_init() step that creates this
            # mapping. The base CodeSage encoder has no tied weights, so an
            # empty mapping is the correct compatibility value.
            pretrained_model = getattr(modeling_utils, "PreTrainedModel", None)
            if pretrained_model is not None:
                if not hasattr(pretrained_model, "all_tied_weights_keys"):
                    pretrained_model.all_tied_weights_keys = {}

                self._patch_codesage_head_mask(pretrained_model)

        elif self._is_codesage_model():
            pretrained_model = getattr(modeling_utils, "PreTrainedModel", None)
            if pretrained_model is not None:
                self._patch_codesage_head_mask(pretrained_model)

    def _patch_codesage_head_mask(self, pretrained_model: type) -> None:
        if hasattr(pretrained_model, "get_head_mask"):
            return

        def get_head_mask(model: object, head_mask: object, num_hidden_layers: int, is_attention_chunked: bool = False) -> object:
            if head_mask is None:
                return [None] * num_hidden_layers

            if head_mask.dim() == 1:
                head_mask = head_mask.unsqueeze(0).unsqueeze(0).unsqueeze(-1).unsqueeze(-1)
                head_mask = head_mask.expand(num_hidden_layers, -1, -1, -1, -1)
            elif head_mask.dim() == 2:
                head_mask = head_mask.unsqueeze(1).unsqueeze(-1).unsqueeze(-1)
            else:
                raise ValueError(f"head_mask.dim != 1 or 2, instead {head_mask.dim()}")

            head_mask = head_mask.to(dtype=model.dtype)
            if is_attention_chunked:
                head_mask = head_mask.unsqueeze(-1)
            return head_mask

        pretrained_model.get_head_mask = get_head_mask
