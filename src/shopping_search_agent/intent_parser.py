from __future__ import annotations

import re

from .llm import LLMClient
from .models import Intent


class IntentParser:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def parse(self, user_query: str) -> Intent:
        system_prompt = (
            "Extract shopping intent as JSON with keys: "
            "product_type(string), attributes(object), budget(string|null), usage(string|null). "
            "Do not invent details not present in the user query."
        )
        user_prompt = f"User shopping request: {user_query}"

        try:
            data = self._llm.complete_json(system_prompt, user_prompt)
            return Intent(
                original_query=user_query,
                product_type=str(data.get("product_type") or "general product"),
                attributes=data.get("attributes") or {},
                budget=data.get("budget"),
                usage=data.get("usage"),
            )
        except Exception:
            return self._heuristic_parse(user_query)

    def _heuristic_parse(self, query: str) -> Intent:
        lowered = query.lower()
        budget_match = re.search(r"(\$|€|£)?\s?\d{2,6}", lowered)
        usage = "daily use" if "daily" in lowered else None
        product_type = "general product"
        for candidate in ["laptop", "phone", "sneaker", "running shoes", "headphones", "monitor", "tablet"]:
            if candidate in lowered:
                product_type = candidate
                break
        attrs = {}
        for token in ["men", "women", "kids", "gaming", "wireless", "4k", "cheap", "premium"]:
            if token in lowered:
                attrs[token] = "true"
        return Intent(
            original_query=query,
            product_type=product_type,
            attributes=attrs,
            budget=budget_match.group(0) if budget_match else None,
            usage=usage,
        )
