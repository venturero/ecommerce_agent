from __future__ import annotations

from .llm import LLMClient
from .models import SearchResult

_STOCK_PROMPT = (
    "For each product line, decide if it is in stock from metadata only (title, snippet, price, url). "
    "Return JSON: {\"items\":[{\"id\":0,\"in_stock\":true|false|null},...]}. "
    "id must match the line id. Use false only when clearly sold out or unavailable; "
    "true when clearly buyable; null when unknown."
)


class StockChecker:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def annotate(self, results: list[SearchResult]) -> list[SearchResult]:
        if not results:
            return results
        lines = [
            f"{i}|title={r.title}|snippet={r.snippet}|price={r.price_display}|url={r.url}"
            for i, r in enumerate(results)
        ]
        try:
            data = self._llm.complete_json(_STOCK_PROMPT, "\n".join(lines))
            for item in data.get("items") or []:
                idx = int(item["id"])
                if idx < 0 or idx >= len(results):
                    continue
                value = item.get("in_stock")
                if value is True:
                    results[idx].in_stock = True
                elif value is False:
                    results[idx].in_stock = False
                elif value is None:
                    results[idx].in_stock = None
        except Exception:
            pass
        return results
