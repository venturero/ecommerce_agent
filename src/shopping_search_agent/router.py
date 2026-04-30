from __future__ import annotations

from .llm import LLMClient
from .models import Route


class SemanticRouter:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def route(self, user_query: str) -> Route:
        system_prompt = (
            "You are a strict classifier. Return JSON with key `route` only. "
            "Valid routes: shopping or chitchat. shopping means user wants product discovery, "
            "comparison, or purchase-oriented recommendations."
        )
        user_prompt = f"Query: {user_query}"
        try:
            parsed = self._llm.complete_json(system_prompt, user_prompt)
            value = str(parsed.get("route", "")).lower().strip()
            if value in ("shopping", "chitchat"):
                return value  # type: ignore[return-value]
        except Exception:
            pass

        fallback_terms = (
            "buy",
            "price",
            "cheap",
            "best",
            "recommend",
            "for men",
            "for women",
            "laptop",
            "shoe",
            "phone",
            "headphone",
            "trendyol",
        )
        lowered = user_query.lower()
        return "shopping" if any(term in lowered for term in fallback_terms) else "chitchat"
