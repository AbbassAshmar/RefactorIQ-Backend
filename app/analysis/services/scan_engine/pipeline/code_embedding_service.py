from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Protocol

logger = logging.getLogger(__name__)


class CodeEmbeddingProvider(Protocol):
    model_id: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode code snippets into dense vectors."""


class CodeEmbeddingService:
    """Lazy Transformers adapter for code embedding models."""

    DEFAULT_MODEL_ID = "jinaai/jina-embeddings-v2-base-code"
    DEFAULT_POOLING_MODE = "cls"
    SUPPORTED_POOLING_MODES = frozenset(
        {"cls", "mean", "max", "mean_sqrt_len", "last_token"}
    )

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        model_path: str | Path | None = None,
        batch_size: int = 8,
        device: str | None = None,
        max_length: int = 1024,
        trust_remote_code: bool = True,
        local_files_only: bool = False,
        pooling_mode: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.model_path = Path(model_path).expanduser().resolve() if model_path else None
        if batch_size < 1:
            raise ValueError("Embedding batch size must be at least 1")
        if max_length < 1:
            raise ValueError("Embedding max length must be at least 1")

        self.batch_size = batch_size
        self.device = device
        self.max_length = max_length
        self.trust_remote_code = trust_remote_code
        self.local_files_only = local_files_only
        self.pooling_mode = pooling_mode or self._default_pooling_mode()
        if self.pooling_mode not in self.SUPPORTED_POOLING_MODES:
            raise ValueError(f"Unsupported embedding pooling mode: {self.pooling_mode}")
        self._metadata_max_length: int | None = None
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

        # Group similarly sized snippets to avoid padding every item to an
        # unrelated long function. Restore the caller's order before returning.
        indexed_texts = sorted(enumerate(prepared), key=lambda item: len(item[1]))
        vectors_by_index: list[list[float] | None] = [None] * len(prepared)
        batch_count = (len(indexed_texts) + self.batch_size - 1) // self.batch_size

        for start in range(0, len(indexed_texts), self.batch_size):
            indexed_batch = indexed_texts[start : start + self.batch_size]
            batch = [text for _, text in indexed_batch]
            batch_number = start // self.batch_size + 1
            batch_started = perf_counter()
            logger.info(
                "[EMBEDDINGS BATCH STARTED] model=%s batch=%d/%d item_count=%d",
                self.model_id,
                batch_number,
                batch_count,
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
                sequence_length = int(encoded["input_ids"].shape[1])
                encoded = {key: value.to(self.device) for key, value in encoded.items()}
                if self._is_jina_v2_model():
                    # This is a single-segment encoder. Supplying the segment
                    # IDs avoids a legacy JinaBERT buffer incompatibility with
                    # current Transformers while preserving model semantics.
                    encoded["token_type_ids"] = self._torch.zeros_like(
                        encoded["input_ids"]
                    )
                encoded.setdefault(
                    "position_ids",
                    self._position_ids_like(encoded["input_ids"]),
                )

                inference_context = getattr(
                    self._torch,
                    "inference_mode",
                    self._torch.no_grad,
                )
                with inference_context():
                    outputs = self._model(**encoded)
                    hidden_states = self._last_hidden_state(outputs)
                    pooled = self._pool_hidden_states(outputs, hidden_states, encoded)
                    pooled = self._torch.nan_to_num(pooled, nan=0.0, posinf=0.0, neginf=0.0)
                    pooled = self._functional.normalize(pooled, p=2, dim=1)
                    pooled = self._torch.nan_to_num(pooled, nan=0.0, posinf=0.0, neginf=0.0)

                batch_vectors = pooled.detach().cpu().float().tolist()
                for (original_index, _), vector in zip(
                    indexed_batch,
                    batch_vectors,
                    strict=True,
                ):
                    vectors_by_index[original_index] = [float(value) for value in vector]
            except Exception:
                logger.exception(
                    "[EMBEDDINGS BATCH FAILED] model=%s batch=%d/%d item_count=%d",
                    self.model_id,
                    batch_number,
                    batch_count,
                    len(batch),
                )
                raise

            logger.info(
                "[EMBEDDINGS BATCH COMPLETED] model=%s batch=%d/%d item_count=%d sequence_length=%d elapsed_seconds=%.3f",
                self.model_id,
                batch_number,
                batch_count,
                len(batch),
                sequence_length,
                perf_counter() - batch_started,
            )

        if any(vector is None for vector in vectors_by_index):
            raise RuntimeError(f"Model {self.model_id} did not return every requested embedding")

        result = [vector for vector in vectors_by_index if vector is not None]
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
            from transformers import AutoConfig, AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Semantic duplication analysis requires torch and transformers"
            ) from exc

        self.device = self._select_device(self.device)
        model_source = self._model_source()
        self._load_sentence_transformer_metadata()
        logger.info(
            "[EMBEDDINGS MODEL CONFIGURED] model=%s device=%s pooling=%s max_length=%d",
            self.model_id,
            self.device,
            self.pooling_mode,
            self._effective_max_length(),
        )
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

        model_config = AutoConfig.from_pretrained(
            model_source,
            trust_remote_code=self.trust_remote_code,
            local_files_only=self.local_files_only,
        )
        self._apply_model_config_compatibility(model_config)
        model = AutoModel.from_pretrained(
            model_source,
            config=model_config,
            trust_remote_code=self.trust_remote_code,
            local_files_only=self.local_files_only,
        )
        model.to(self.device)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch
        self._functional = functional
        logger.info(
            "[EMBEDDINGS LOADED] model=%s device=%s pooling=%s max_length=%d",
            self.model_id,
            self.device,
            self.pooling_mode,
            self._effective_max_length(),
        )

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
        _outputs: object,
        hidden_states: object,
        encoded: dict[str, object],
    ) -> object:
        if self.pooling_mode == "cls":
            return hidden_states[:, 0]

        attention_mask = encoded.get("attention_mask")
        if attention_mask is None:
            if self.pooling_mode == "last_token":
                return hidden_states[:, -1]
            if self.pooling_mode == "max":
                return hidden_states.max(dim=1).values
            return hidden_states.mean(dim=1)

        mask = attention_mask.unsqueeze(-1).to(dtype=hidden_states.dtype)
        token_count = mask.sum(dim=1).clamp_min(1.0)

        if self.pooling_mode == "mean":
            return (hidden_states * mask).sum(dim=1) / token_count

        if self.pooling_mode == "mean_sqrt_len":
            return (hidden_states * mask).sum(dim=1) / token_count.sqrt()

        if self.pooling_mode == "max":
            minimum = self._torch.finfo(hidden_states.dtype).min
            return hidden_states.masked_fill(mask == 0, minimum).max(dim=1).values

        if self.pooling_mode == "last_token":
            if bool(attention_mask[:, -1].all()):
                return hidden_states[:, -1]
            last_indices = attention_mask.long().sum(dim=1).sub(1).clamp_min(0)
            batch_indices = self._torch.arange(
                hidden_states.shape[0],
                device=hidden_states.device,
            )
            return hidden_states[batch_indices, last_indices]

        raise RuntimeError(f"Unsupported embedding pooling mode: {self.pooling_mode}")

    def _effective_max_length(self) -> int:
        limits = [self.max_length]
        for value in (
            self._metadata_max_length,
            getattr(getattr(self._model, "config", None), "max_position_embeddings", None),
            getattr(self._tokenizer, "model_max_length", None),
        ):
            if isinstance(value, int) and 0 < value < 1_000_000:
                limits.append(value)
        return min(limits)

    def _load_sentence_transformer_metadata(self) -> None:
        self._metadata_max_length = None

        if self.model_path is None:
            return

        sentence_config = self._read_json_file(
            self.model_path / "sentence_bert_config.json"
        )
        configured_length = sentence_config.get("max_seq_length")
        if isinstance(configured_length, int) and configured_length > 0:
            self._metadata_max_length = configured_length

        pooling_config = self._read_json_file(
            self.model_path / "1_Pooling" / "config.json"
        )
        if not pooling_config:
            return

        enabled_modes = [
            mode
            for key, mode in (
                ("pooling_mode_cls_token", "cls"),
                ("pooling_mode_mean_tokens", "mean"),
                ("pooling_mode_max_tokens", "max"),
                ("pooling_mode_mean_sqrt_len_tokens", "mean_sqrt_len"),
                ("pooling_mode_lasttoken", "last_token"),
            )
            if pooling_config.get(key) is True
        ]
        if len(enabled_modes) != 1:
            raise RuntimeError(
                f"Local embedding model must configure exactly one supported pooling mode; "
                f"found {enabled_modes or 'none'} in {self.model_path / '1_Pooling' / 'config.json'}"
            )
        self.pooling_mode = enabled_modes[0]

    def _read_json_file(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {}

        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid embedding model metadata file: {path}") from exc

        if not isinstance(value, dict):
            raise RuntimeError(f"Embedding model metadata must be a JSON object: {path}")
        return value

    def _default_pooling_mode(self) -> str:
        model_source = f"{self.model_id} {self.model_path or ''}".lower()
        if "codesage" in model_source or "jina-embeddings-v2-base-code" in model_source:
            return "mean"
        return self.DEFAULT_POOLING_MODE

    def _apply_model_config_compatibility(self, model_config: object) -> None:
        # Older remote BERT configs relied on PretrainedConfig to supply these
        # encoder defaults. Transformers 4.56 no longer creates all of them.
        for name, value in (
            ("is_decoder", False),
            ("add_cross_attention", False),
            ("chunk_size_feed_forward", 0),
        ):
            if not hasattr(model_config, name):
                setattr(model_config, name, value)

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

    def _is_jina_v2_model(self) -> bool:
        model_source = f"{self.model_id} {self.model_path or ''}".lower()
        return "jina-embeddings-v2-base-code" in model_source

    def _apply_transformers_compatibility_patches(self) -> None:
        try:
            import transformers
            import transformers.modeling_utils as modeling_utils
            import transformers.pytorch_utils as pytorch_utils
        except Exception:
            return

        if not hasattr(modeling_utils, "Conv1D"):
            try:
                from transformers.pytorch_utils import Conv1D
            except Exception:
                pass
            else:
                modeling_utils.Conv1D = Conv1D

        if not hasattr(pytorch_utils, "find_pruneable_heads_and_indices"):
            # JinaBERT still imports this Transformers 4 helper even though
            # current releases removed it. Inference does not prune heads, but
            # the symbol must exist for the remote model module to import.
            def find_pruneable_heads_and_indices(
                heads: list[int],
                n_heads: int,
                head_size: int,
                already_pruned_heads: set[int],
            ) -> tuple[set[int], object]:
                import torch

                mask = torch.ones(n_heads, head_size)
                requested_heads = set(heads) - already_pruned_heads
                for head in requested_heads:
                    shifted_head = head - sum(
                        1 if pruned_head < head else 0
                        for pruned_head in already_pruned_heads
                    )
                    mask[shifted_head] = 0
                keep_mask = mask.view(-1).contiguous().eq(1)
                indices = torch.arange(len(keep_mask))[keep_mask].long()
                return requested_heads, indices

            pytorch_utils.find_pruneable_heads_and_indices = (
                find_pruneable_heads_and_indices
            )

        pretrained_model = getattr(modeling_utils, "PreTrainedModel", None)
        if pretrained_model is not None:
            self._patch_legacy_head_mask(pretrained_model)

        transformers_version = getattr(transformers, "__version__", "")
        if self._is_codesage_model() and transformers_version.startswith("5."):
            # CodeSage's remote model calls init_weights() directly and does
            # not run the Transformers 5 post_init() step that creates this
            # mapping. The base CodeSage encoder has no tied weights, so an
            # empty mapping is the correct compatibility value.
            if pretrained_model is not None:
                if not hasattr(pretrained_model, "all_tied_weights_keys"):
                    pretrained_model.all_tied_weights_keys = {}

    def _patch_legacy_head_mask(self, pretrained_model: type) -> None:
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
