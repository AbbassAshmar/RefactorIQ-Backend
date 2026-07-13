"""Shared provider abstractions for LLM-backed application features."""

import logging
from typing import Any, Protocol

from google import genai
from google.genai import errors as genai_errors

from app.core.exceptions.domain_exceptions import ExternalDependencyError

logger = logging.getLogger(__name__)


class LlmProvider(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class GeminiLlmProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    def generate(self, prompt: str) -> str:
        if not self._api_key:
            raise ExternalDependencyError("Gemini API key is not configured")

        client = None
        should_close = False
        try:
            client = self._client or genai.Client(api_key=self._api_key)
            should_close = self._client is None
            interaction = client.interactions.create(
                model=self._model,
                input=prompt,
            )
            text = (interaction.output_text or "").strip()
            if not text:
                raise ExternalDependencyError("Gemini returned no summary text")
            return text
        except ExternalDependencyError:
            raise
        except (genai_errors.APIError, ValueError, TypeError, AttributeError) as exc:
            logger.error("Error generating LLM response", exc_info=True)
            raise ExternalDependencyError("Unable to generate LLM response") from exc
        finally:
            if should_close and client is not None:
                client.close()
