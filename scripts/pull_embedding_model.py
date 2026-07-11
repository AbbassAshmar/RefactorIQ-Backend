from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from huggingface_hub import snapshot_download


DEFAULT_MODEL_ID = "Salesforce/SFR-Embedding-Code-400M_R"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / ".models" / "sfr-embedding-code-400m"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a Hugging Face model repo into a local model directory.",
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

    print(f"Downloading model repo: {args.model_id}")
    print(f"Model directory: {model_dir}")
    print(f"Revision: {args.revision}")

    last_error: Exception | None = None

    for attempt in range(1, args.retries + 1):
        try:
            snapshot_download(
                repo_id=args.model_id,
                revision=args.revision,
                token=token,
                local_dir=str(model_dir),
                local_dir_use_symlinks=False,
                max_workers=1,
                force_download=False,
            )

            print("Model downloaded successfully.")
            print(f"Model path: {model_dir}")
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
                print(f"Retrying in {args.sleep} seconds...")
                time.sleep(args.sleep)

    print(f"Failed after {args.retries} attempts.", file=sys.stderr)
    print(f"Last error: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())