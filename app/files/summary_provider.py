from __future__ import annotations

from typing import Protocol

import httpx

from app.core.exceptions.domain_exceptions import ExternalDependencyError


class FileSummaryProvider(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class GeminiFileSummaryProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        api_base_url: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._api_base_url = api_base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client

    def generate(self, prompt: str) -> str:
        if not self._api_key:
            raise ExternalDependencyError("Gemini API key is not configured")

        client = self._client or httpx.Client(timeout=self._timeout_seconds)
        should_close = self._client is None
        try:
            response = client.post(
                f"{self._api_base_url}/models/{self._model}:generateContent",
                headers={"x-goog-api-key": self._api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 300,
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
            candidates = payload.get("candidates") or []
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "".join(str(part.get("text", "")) for part in parts).strip()
            if not text:
                raise ExternalDependencyError("Gemini returned no summary text")
            return text
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            raise ExternalDependencyError("Unable to generate file summary") from exc
        finally:
            if should_close:
                client.close()
