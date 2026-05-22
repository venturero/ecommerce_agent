from __future__ import annotations

from urllib.parse import urlparse

from .market import (
    market_for_search,
    merchant_matches_trusted,
    price_exceeds_budget,
    url_matches_trusted_retailer,
)
from .models import Intent, ParseStatus
from .parse_policy import apply_budget_filter
from .serpapi_client import SerpApiClient, SerpApiSearchError


class ImmersiveProductResolver:
    def __init__(self, client: SerpApiClient, max_lookups: int) -> None:
        self._client = client
        self._max_lookups = max_lookups
        self._calls_by_session: dict[str, int] = {}

    @staticmethod
    def _session_key(session_id: str | None) -> str:
        return session_id or "_anonymous"

    def resolve_store(
        self,
        token: str,
        intent: Intent,
        *,
        parse_status: ParseStatus,
        session_id: str | None = None,
        title: str = "",
        merchant_hint: str | None = None,
    ) -> dict | None:
        key = self._session_key(session_id)
        if self._calls_by_session.get(key, 0) >= self._max_lookups:
            return None
        self._calls_by_session[key] = self._calls_by_session.get(key, 0) + 1

        market = market_for_search(intent)
        try:
            payload = self._client.search(
                {
                    "engine": "google_immersive_product",
                    "page_token": token,
                    "more_stores": "true",
                    "hl": market.language,
                    "gl": market.country_code,
                }
            )
        except SerpApiSearchError:
            return None
        stores = payload.get("product_results", {}).get("stores") or payload.get("stores") or []
        best: dict | None = None
        best_score = -1.0

        for store in stores:
            link = str(store.get("link", "")).strip()
            if not link or not url_matches_trusted_retailer(link, market):
                continue

            details = " ".join(store.get("details_and_offers") or [])

            extracted = store.get("extracted_price")
            currency = "TRY" if market.country_code == "tr" else "USD"
            if (
                apply_budget_filter(parse_status)
                and extracted is not None
                and price_exceeds_budget(
                    float(extracted),
                    currency,
                    intent.budget_amount,
                    intent.budget_currency,
                )
            ):
                continue

            score = 1.0
            name = str(store.get("name", ""))
            if merchant_hint and merchant_hint.lower() in name.lower():
                score += 1.5
            if merchant_matches_trusted(name):
                score += 0.5
            host = urlparse(link).netloc.lower()
            if market.country_code == "tr" and host.endswith("amazon.com.tr"):
                score += 0.4
            if "trendyol" in host:
                score += 0.6
            if "hepsiburada" in host:
                score += 0.5

            if score > best_score:
                best_score = score
                best = {
                    "url": link,
                    "title": str(store.get("title") or title),
                    "price_display": store.get("price"),
                    "extracted_price": float(extracted) if extracted is not None else None,
                    "price_currency": currency,
                    "merchant": name,
                    "snippet": details or str(store.get("payment_methods") or ""),
                }

        return best
