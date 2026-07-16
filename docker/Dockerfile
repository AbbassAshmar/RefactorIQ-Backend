# syntax=docker/dockerfile:1.7

FROM python:3.11-slim

WORKDIR /backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# The container has no CUDA runtime, so use PyTorch's CPU wheel. Keep pip's
# cache in a BuildKit mount so a later build can reuse completed downloads.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install \
        --disable-pip-version-check \
        --timeout=300 \
        --retries=10 \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
