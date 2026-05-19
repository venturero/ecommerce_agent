from __future__ import annotations

import json
from abc import ABC, abstractmethod

from .config import Settings


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class OpenAILLMClient(LLMClient):
    TEMPERATURE = 0

    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
        self._model = settings.openai_model
        self._client = OpenAI(api_key=settings.openai_api_key)

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.TEMPERATURE,
            text={"format": {"type": "json_object"}},
        )
        return json.loads(response.output_text)

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.TEMPERATURE,
        )
        return response.output_text.strip()


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
