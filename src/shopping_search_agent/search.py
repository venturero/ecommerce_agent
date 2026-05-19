from __future__ import annotations

from urllib.parse import urlparse

import requests

from .config import Settings
from .immersive import ImmersiveProductResolver
from .market import (
    amazon_domain_for,
    budget_limit_try,
    market_for_search,
    merchant_matches_trusted,
    parse_price_display,
    price_exceeds_budget,
    url_matches_trusted_retailer,
)
from .models import Intent, ParseStatus, SearchResult
from .parse_policy import apply_budget_filter
from .serpapi_client import SerpApiClient, SerpApiSearchError
from .trendyol_search import TrendyolNativeSearch


class MultiEngineRetriever:
    """Amazon (SerpApi) + Trendyol (native sr search; SerpApi fallback)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = SerpApiClient(settings)
        self._immersive = ImmersiveProductResolver(self._client, settings.max_immersive_lookups)
        self._trendyol = TrendyolNativeSearch(
            timeout=settings.trendyol_request_timeout,
            max_results=settings.trendyol_max_results_per_query,
        )

    def search_all(
        self,
        intent: Intent,
        *,
        primary_query: str,
        trendyol_queries: list[str],
        parse_status: ParseStatus,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []

        if self._settings.use_amazon_search:
            results.extend(self._safe(self._search_amazon, primary_query, intent, parse_status))

        trendyol_results: list[SearchResult] = []
        if self._settings.use_trendyol_native:
            for query in trendyol_queries:
                trendyol_results.extend(self._safe_trendyol(query, intent, parse_status))
        results.extend(trendyol_results)

        if self._settings.use_trendyol_serpapi_fallback and len(trendyol_results) < self._settings.trendyol_fallback_min_results:
            for query in trendyol_queries[:2]:
                results.extend(
                    self._safe(self._search_trendyol_serpapi_fallback, query, intent, parse_status)
                )

        return results

    def _safe(self, fn, query: str, intent: Intent, parse_status: ParseStatus) -> list[SearchResult]:
        try:
            return fn(query, intent, parse_status)
        except (SerpApiSearchError, requests.RequestException):
            return []

    def _safe_trendyol(self, query: str, intent: Intent, parse_status: ParseStatus) -> list[SearchResult]:
        try:
            return self._trendyol.search(query, intent, parse_status)
        except requests.RequestException:
            return []

    def _search_trendyol_serpapi_fallback(
        self, query: str, intent: Intent, parse_status: ParseStatus
    ) -> list[SearchResult]:
        """SerpApi fallback: Google Shopping filtered to Trendyol merchant links only."""
        market = market_for_search(intent)
        params: dict = {
            "engine": "google_shopping",
            "q": f"{query} site:trendyol.com",
            "gl": market.country_code,
            "hl": market.language,
            "num": self._settings.shopping_results_per_query,
        }
        if apply_budget_filter(parse_status):
            max_try = budget_limit_try(intent.budget_amount, intent.budget_currency)
            if max_try is not None and market.country_code == "tr":
                params["max_price"] = max_try

        payload = self._client.search(params)
        parsed: list[SearchResult] = []
        items = payload.get("shopping_results") or []
        for block in payload.get("categorized_shopping_results") or []:
            items.extend(block.get("shopping_results") or [])

        for item in items:
            merchant = str(item.get("source", "")).strip()
            if merchant and "trendyol" not in merchant.lower():
                continue

            title = str(item.get("title", "")).strip()
            snippet = str(item.get("snippet", "") or "").strip()
            price_display = item.get("price")
            extracted = item.get("extracted_price")
            currency = "TRY" if market.country_code == "tr" else "USD"
            if extracted is not None:
                extracted = float(extracted)
            elif price_display:
                extracted, currency = parse_price_display(str(price_display), market.country_code)

            extensions = " ".join(item.get("extensions") or [])

            url = self._pick_trendyol_shopping_url(
                item, intent, parse_status, title=title, merchant=merchant
            )
            if not url:
                continue
            if apply_budget_filter(parse_status) and price_exceeds_budget(
                extracted, currency, intent.budget_amount, intent.budget_currency
            ):
                continue

            parsed.append(
                SearchResult(
                    title=title,
                    snippet=snippet or extensions,
                    url=url,
                    domain=urlparse(url).netloc.lower(),
                    source_query=query,
                    source_engine="google_shopping",
                    extracted_price=extracted,
                    price_currency=currency,
                    price_display=str(price_display) if price_display else None,
                    merchant=merchant or "Trendyol",
                )
            )
        return parsed

    def _pick_trendyol_shopping_url(
        self,
        item: dict,
        intent: Intent,
        parse_status: ParseStatus,
        *,
        title: str,
        merchant: str | None,
    ) -> str | None:
        market = market_for_search(intent)
        for key in ("link", "product_link"):
            candidate = str(item.get(key, "")).strip()
            if candidate and "trendyol.com" in candidate and url_matches_trusted_retailer(candidate, market):
                if "-p-" in candidate:
                    return candidate

        token = item.get("immersive_product_page_token")
        if token and merchant_matches_trusted(merchant):
            resolved = self._immersive.resolve_store(
                str(token),
                intent,
                parse_status=parse_status,
                title=title,
                merchant_hint=merchant or "Trendyol",
            )
            if resolved and "trendyol.com" in str(resolved["url"]):
                return str(resolved["url"])
        return None

    def _search_amazon(self, query: str, intent: Intent, parse_status: ParseStatus) -> list[SearchResult]:
        market = market_for_search(intent)
        domain = amazon_domain_for(market)
        payload = self._client.search(
            {
                "engine": "amazon",
                "amazon_domain": domain,
                "k": query,
            }
        )
        parsed: list[SearchResult] = []
        for item in payload.get("organic_results") or []:
            link = str(item.get("link_clean") or item.get("link") or "").strip()
            if not link or "/dp/" not in link:
                continue
            title = str(item.get("title", "")).strip()
            price_display = item.get("price")
            extracted = item.get("extracted_price")
            currency = "TRY" if domain.endswith(".com.tr") else "USD"
            if extracted is not None:
                extracted = float(extracted)
            elif price_display:
                extracted, currency = parse_price_display(str(price_display), market.country_code)

            delivery = " ".join(item.get("delivery") or []) if isinstance(item.get("delivery"), list) else ""
            offers = " ".join(item.get("offers") or []) if isinstance(item.get("offers"), list) else ""
            availability = str(item.get("availability", "")).strip()
            snippet = " | ".join(p for p in (delivery, offers, availability) if p)
            if apply_budget_filter(parse_status) and price_exceeds_budget(
                extracted, currency, intent.budget_amount, intent.budget_currency
            ):
                continue

            parsed.append(
                SearchResult(
                    title=title,
                    snippet=snippet,
                    url=link,
                    domain=urlparse(link).netloc.lower(),
                    source_query=query,
                    source_engine="amazon",
                    extracted_price=extracted,
                    price_currency=currency,
                    price_display=str(price_display) if price_display else None,
                    merchant="Amazon",
                )
            )
        return parsed


SerpApiSearchRetriever = MultiEngineRetriever
