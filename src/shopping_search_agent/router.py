from __future__ import annotations

from .llm import LLMClient
from .models import Route

_ROUTE_SYSTEM_PROMPT = """You classify user messages for a shopping search assistant.

Return JSON with exactly one key: "route".
Allowed values:
- "shopping" — the user wants to find, compare, or buy products, including when they add
  personal context (age, appearance, fit, style) together with a product request.
  Examples: "I need a white t-shirt for men", "cheaper headphones", "compare the top two".
- "chitchat" — greetings, jokes, general knowledge, or conversation with no product search goal.

When the message mentions a product to find or buy, always use "shopping"."""


class SemanticRouter:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def route(self, user_query: str) -> Route:
        if not user_query.strip():
            return "chitchat"

        try:
            parsed = self._llm.complete_json(_ROUTE_SYSTEM_PROMPT, f"User message:\n{user_query}")
            value = str(parsed.get("route", "")).lower().strip()
            if value in ("shopping", "chitchat"):
                return value  # type: ignore[return-value]
        except Exception:
            pass

        # Shopping-first default when the classifier returns invalid JSON (offline / provider glitch).
        return "shopping"
