from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download


DEFAULT_MODEL_ID = "jinaai/jina-embeddings-v2-base-code"
DEFAULT_MODEL_DIR = (
    Path(__file__).resolve().parents[1] / ".models" / "jina-embeddings-v2-base-code"
)
MODEL_CODE_REPO = "jinaai/jina-bert-v2-qk-post-norm"
MODEL_CODE_FILES = ("configuration_bert.py", "modeling_bert.py")
REQUIRED_MODEL_FILES = (
    "1_Pooling/config.json",
    "README.md",
    "config.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download the Jina v2 code embedding model into a local directory.",
    )
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--revision", default="main")
    parser.add_argument("--retries", type=int, default=20)
    parser.add_argument("--sleep", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    model_dir = Path(args.model_dir).expanduser().resolve()
    model_dir.mkdir(parents=True, exist_ok=True)

    token = os.environ.get("HF_TOKEN")
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "60"
    os.environ["HF_HUB_ETAG_TIMEOUT"] = "30"

    print(f"Downloading model repo: {args.model_id}", flush=True)
    print(f"Model directory: {model_dir}", flush=True)
    print(f"Revision: {args.revision}", flush=True)

    last_error: Exception | None = None
    for attempt in range(1, args.retries + 1):
        try:
            snapshot_download(
                repo_id=args.model_id,
                revision=args.revision,
                token=token,
                local_dir=str(model_dir),
                max_workers=1,
                force_download=False,
                allow_patterns=list(REQUIRED_MODEL_FILES),
            )

            for filename in MODEL_CODE_FILES:
                hf_hub_download(
                    repo_id=MODEL_CODE_REPO,
                    filename=filename,
                    revision=args.revision,
                    token=token,
                    local_dir=str(model_dir),
                    force_download=False,
                )

            _make_remote_code_local(model_dir / "config.json")
            print("Model downloaded successfully.", flush=True)
            print(f"Model path: {model_dir}", flush=True)
            return 0
        except KeyboardInterrupt:
            print("Cancelled by user.", file=sys.stderr)
            return 130
        except Exception as exc:
            last_error = exc
            print(
                f"Download attempt {attempt}/{args.retries} failed: {exc}",
                file=sys.stderr,
            )
            if attempt < args.retries:
                print(f"Retrying in {args.sleep} seconds...", flush=True)
                time.sleep(args.sleep)

    print(f"Failed after {args.retries} attempts.", file=sys.stderr)
    print(f"Last error: {last_error}", file=sys.stderr)
    return 1


def _make_remote_code_local(config_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    auto_map = config.get("auto_map")
    if not isinstance(auto_map, dict):
        raise RuntimeError(f"Model config has no auto_map object: {config_path}")

    for task, reference in auto_map.items():
        if isinstance(reference, str) and "--" in reference:
            auto_map[task] = reference.split("--", maxsplit=1)[1]

    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
