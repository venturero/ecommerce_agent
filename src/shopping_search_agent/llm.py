from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TypeVar

from .config import Settings
from .retry import call_with_retry, is_transient_llm_error

T = TypeVar("T")


class LLMTimeoutError(TimeoutError):
    """Raised when an LLM provider does not respond within the configured timeout."""


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


def _is_timeout_error(err: BaseException) -> bool:
    if isinstance(err, (LLMTimeoutError, TimeoutError)):
        return True
    try:
        from openai import APITimeoutError

        if isinstance(err, APITimeoutError):
            return True
    except ImportError:
        pass
    try:
        import httpx

        if isinstance(err, httpx.TimeoutException):
            return True
    except ImportError:
        pass
    cause = err.__cause__
    return cause is not None and cause is not err and _is_timeout_error(cause)


def _raise_timeout_from(err: BaseException) -> None:
    if _is_timeout_error(err):
        raise LLMTimeoutError("LLM request timed out") from err


class OpenAILLMClient(LLMClient):
    TEMPERATURE = 0

    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
        self._model = settings.openai_model
        self._timeout = settings.openai_request_timeout
        self._client = OpenAI(api_key=settings.openai_api_key, timeout=self._timeout)

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return self._call(
            lambda: json.loads(
                self._client.responses.create(
                    model=self._model,
                    input=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.TEMPERATURE,
                    text={"format": {"type": "json_object"}},
                    timeout=self._timeout,
                ).output_text
            )
        )

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        return self._call(
            lambda: self._client.responses.create(
                model=self._model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.TEMPERATURE,
                timeout=self._timeout,
            )
            .output_text.strip()
        )

    def _call(self, fn: Callable[[], T]) -> T:
        def _run() -> T:
            try:
                return fn()
            except Exception as err:
                _raise_timeout_from(err)
                raise

        try:
            return call_with_retry(_run, is_retryable=is_transient_llm_error)
        except Exception as err:
            _raise_timeout_from(err)
            raise


class HeuristicLLMClient(LLMClient):
    """
    Offline fallback for local testing when no provider key exists.
    This does not replace an LLM in production.
    """

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        _ = system_prompt
        return {"raw_text": user_prompt}

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt
        return user_prompt


def build_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider.lower() == "openai" and settings.openai_api_key:
        return OpenAILLMClient(settings)
    return HeuristicLLMClient()
