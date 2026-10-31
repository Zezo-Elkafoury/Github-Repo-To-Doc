"""OpenRouter and NVIDIA NIM model integrations via langchain-openai.

Configurable through environment variables:
- OpenRouter: OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL
- NVIDIA NIM: NIM_API_KEY, NIM_MODEL, NIM_BASE_URL

Implements bounded retry with exponential backoff for transient provider
failures and safe handling of invalid structured output.
"""

from __future__ import annotations

import logging
import random
import time
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from github_to_docs.config import settings, validate_credentials

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# NVIDIA NIM models available for selection.
NIM_MODELS = [
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-405b-instruct",
    "nvidia/nemotron-4-340b-reward",
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/mixtral-8x22b-instruct-v0.1",
    "google/gemma-2-9b-it",
    "google/gemma-2-27b-it",
]


class ModelError(RuntimeError):
    """Raised for unrecoverable model failures."""


class ModelClient:
    """Thin wrapper around langchain-openai ChatOpenAI pointed at OpenRouter."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.2,
        max_retries: int = 3,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
        timeout_seconds: int | None = None,
    ) -> None:
        validate_credentials("openrouter")
        self.model = model or settings.openrouter_model
        self.base_url = base_url or settings.openrouter_base_url
        self.api_key = api_key or settings.openrouter_api_key or ""
        self.temperature = temperature
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.timeout_seconds = timeout_seconds or settings.request_timeout_seconds

        self._llm = ChatOpenAI(
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            temperature=self.temperature,
            timeout=self.timeout_seconds,
            max_retries=0,
        )

    def _sleep_with_backoff(self, attempt: int) -> None:
        backoff = min(
            self.initial_backoff_seconds * (2**attempt),
            self.max_backoff_seconds,
        )
        jitter = random.uniform(0, backoff * 0.2)
        time.sleep(backoff + jitter)

    def generate_text(self, system: str, user: str) -> str:
        """Generate plain text with bounded retries for transient failures."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._llm.invoke(
                    [SystemMessage(content=system), HumanMessage(content=user)]
                )
                content = response.content
                if isinstance(content, str):
                    return content
                return str(content)
            except Exception as exc:
                last_error = exc
                if self._is_retryable(exc) and attempt < self.max_retries:
                    logger.warning(
                        "Model call failed (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                    )
                    self._sleep_with_backoff(attempt)
                    continue
                raise ModelError(f"Model generation failed: {exc}") from exc
        raise ModelError(f"Model generation failed after retries: {last_error}")

    def generate_structured(self, system: str, user: str, schema: type[T]) -> T:
        """Generate structured output validated against a Pydantic schema."""
        parser = PydanticOutputParser(pydantic_object=schema)
        format_instructions = parser.get_format_instructions()

        user_with_format = (
            f"{user}\n\n{format_instructions}\n"
            "Return ONLY the JSON object, no markdown code fences."
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = self.generate_text(system, user_with_format)
                return parser.parse(raw)
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    logger.warning(
                        "Invalid structured output (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                    )
                    user_with_format = (
                        "The previous response was invalid. "
                        "Return ONLY valid JSON matching the schema. "
                        f"{user}\n\n{format_instructions}"
                    )
                    continue
                raise ModelError(f"Invalid structured output after retries: {exc}") from exc
        raise ModelError(f"Invalid structured output after retries: {last_error}")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Classify provider errors as retryable or not."""
        msg = str(exc).lower()
        if any(k in msg for k in ("401", "403", "unauthorized", "forbidden", "invalid_api_key")):
            return False
        if any(
            k in msg for k in ("429", "rate limit", "502", "503", "504", "timeout", "unavailable")
        ):
            return True
        return False


class NimModelClient:
    """Thin wrapper around langchain-openai ChatOpenAI pointed at NVIDIA NIM.

    NVIDIA NIM provides OpenAI-compatible endpoints, so this reuses
    ``ChatOpenAI`` with NVIDIA's base URL and API key. Uses the same
    ``generate_text`` / ``generate_structured`` interface as
    :class:`ModelClient` so planner, generator, and verifier are
    provider-agnostic.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.2,
        max_retries: int = 3,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
        timeout_seconds: int | None = None,
    ) -> None:
        validate_credentials("nim")
        self.model = model or settings.nim_model
        self.base_url = base_url or settings.nim_base_url
        self.api_key = api_key or settings.nim_api_key or ""
        self.temperature = temperature
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.timeout_seconds = timeout_seconds or 120

        self._llm = ChatOpenAI(
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            temperature=self.temperature,
            timeout=self.timeout_seconds,
            max_retries=0,
        )

    def _sleep_with_backoff(self, attempt: int) -> None:
        backoff = min(
            self.initial_backoff_seconds * (2**attempt),
            self.max_backoff_seconds,
        )
        jitter = random.uniform(0, backoff * 0.2)
        time.sleep(backoff + jitter)

    def generate_text(self, system: str, user: str) -> str:
        """Generate plain text with bounded retries for transient failures."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._llm.invoke(
                    [SystemMessage(content=system), HumanMessage(content=user)]
                )
                content = response.content
                if isinstance(content, str):
                    return content
                return str(content)
            except Exception as exc:
                last_error = exc
                if self._is_retryable(exc) and attempt < self.max_retries:
                    logger.warning(
                        "Model call failed (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                    )
                    self._sleep_with_backoff(attempt)
                    continue
                raise ModelError(f"Model generation failed: {exc}") from exc
        raise ModelError(f"Model generation failed after retries: {last_error}")

    def generate_structured(self, system: str, user: str, schema: type[T]) -> T:
        """Generate structured output validated against a Pydantic schema."""
        parser = PydanticOutputParser(pydantic_object=schema)
        format_instructions = parser.get_format_instructions()

        user_with_format = (
            f"{user}\n\n{format_instructions}\n"
            "Return ONLY the JSON object, no markdown code fences."
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = self.generate_text(system, user_with_format)
                return parser.parse(raw)
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    logger.warning(
                        "Invalid structured output (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                    )
                    user_with_format = (
                        "The previous response was invalid. "
                        "Return ONLY valid JSON matching the schema. "
                        f"{user}\n\n{format_instructions}"
                    )
                    continue
                raise ModelError(f"Invalid structured output after retries: {exc}") from exc
        raise ModelError(f"Invalid structured output after retries: {last_error}")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Classify provider errors as retryable or not."""
        msg = str(exc).lower()
        if any(k in msg for k in ("401", "403", "unauthorized", "forbidden", "invalid_api_key")):
            return False
        if any(
            k in msg for k in ("429", "rate limit", "502", "503", "504", "timeout", "unavailable")
        ):
            return True
        return False


def create_model_client(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.2,
    max_retries: int = 3,
    initial_backoff_seconds: float = 1.0,
    max_backoff_seconds: float = 30.0,
    timeout_seconds: int | None = None,
) -> ModelClient | NimModelClient:
    """Factory that returns a model client for the given provider.

    Args:
        provider: "openrouter" or "nim". Defaults to
            ``settings.model_provider``.
        model: Model name override.
        api_key: API key override.
        base_url: Base URL override (OpenRouter only).
        temperature: Sampling temperature.
        max_retries: Maximum retry attempts.
        initial_backoff_seconds: Initial backoff between retries.
        max_backoff_seconds: Maximum backoff cap.
        timeout_seconds: HTTP timeout per request.

    Returns:
        A :class:`ModelClient` (OpenRouter) or :class:`NimModelClient`.
    """
    settings_obj = settings
    provider = provider or settings_obj.model_provider

    if provider == "nim":
        return NimModelClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_retries=max_retries,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
            timeout_seconds=timeout_seconds,
        )

    return ModelClient(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_retries=max_retries,
        initial_backoff_seconds=initial_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
        timeout_seconds=timeout_seconds,
    )


__all__ = [
    "ModelClient",
    "NimModelClient",
    "ModelError",
    "create_model_client",
    "NIM_MODELS",
]
