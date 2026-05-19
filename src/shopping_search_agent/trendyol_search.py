from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import requests

from .market import parse_price_display, price_exceeds_budget
from .models import Intent, ParseStatus, SearchResult
from .parse_policy import apply_budget_filter

TRENDYOL_ORIGIN = "https://www.trendyol.com"
TRENDYOL_SEARCH_URL = f"{TRENDYOL_ORIGIN}/sr"
TRENDYOL_API_URL = (
    f"{TRENDYOL_ORIGIN}/discovery-web-searchgw-service/v2/api/infinite-scroll/sr"
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


@dataclass
class _ParsedProduct:
    title: str
    url: str
    price_display: str | None = None
    extracted_price: float | None = None
    price_currency: str = "TRY"
    brand: str | None = None
    stock_hint: str = ""


class TrendyolNativeSearch:
    """Primary Trendyol discovery via trendyol.com/sr (HTML + embedded JSON / gateway API)."""

    def __init__(self, timeout: int = 30, max_results: int = 24) -> None:
        self._timeout = timeout
        self._max_results = max_results
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)

    def search(self, query: str, intent: Intent, parse_status: ParseStatus) -> list[SearchResult]:
        products: list[_ParsedProduct] = []
        products.extend(self._search_via_api(query))
        if len(products) < 3:
            products.extend(self._search_via_html(query))
        return self._to_results(products, query, intent, parse_status)

    def _search_via_api(self, query: str) -> list[_ParsedProduct]:
        params = {
            "q": query,
            "qt": query,
            "st": query,
            "os": "1",
            "pi": "1",
            "culture": "tr-TR",
            "userGenderId": "2",
            "pId": "0",
            "scoringAlgorithmId": "2",
            "categoryRelevancyEnabled": "false",
            "isLegalRequirementConfirmed": "false",
            "productStampType": "TypeA",
            "searchStrategyType": "DEFAULT",
            "location": "null",
            "sort": "0",
            "sst": "0",
        }
        headers = {
            **DEFAULT_HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{TRENDYOL_SEARCH_URL}?q={quote_plus(query)}&sst=0",
            "Origin": TRENDYOL_ORIGIN,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        try:
            self._session.get(TRENDYOL_ORIGIN, timeout=self._timeout)
            response = self._session.get(
                TRENDYOL_API_URL,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
            if response.status_code != 200:
                return []
            payload = response.json()
        except (requests.RequestException, ValueError):
            return []
        return self._extract_products_from_json(payload)

    def _search_via_html(self, query: str) -> list[_ParsedProduct]:
        url = f"{TRENDYOL_SEARCH_URL}?q={quote_plus(query)}&sst=0"
        try:
            response = self._session.get(url, timeout=self._timeout)
            if response.status_code != 200:
                return []
            html = response.text
        except requests.RequestException:
            return []

        products: list[_ParsedProduct] = []
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if match:
            try:
                payload = json.loads(match.group(1))
                products.extend(self._extract_products_from_json(payload))
            except ValueError:
                pass

        if not products:
            products.extend(self._extract_products_from_urls(html))
        return products

    def _extract_products_from_json(self, payload: object) -> list[_ParsedProduct]:
        found: list[_ParsedProduct] = []
        seen: set[str] = set()
        self._walk_json(payload, found, seen)
        return found

    def _walk_json(self, node: object, found: list[_ParsedProduct], seen: set[str]) -> None:
        if isinstance(node, dict):
            product = self._product_from_dict(node)
            if product and product.url not in seen:
                seen.add(product.url)
                found.append(product)
            for value in node.values():
                self._walk_json(value, found, seen)
        elif isinstance(node, list):
            for item in node:
                self._walk_json(item, found, seen)

    def _product_from_dict(self, node: dict) -> _ParsedProduct | None:
        title = str(
            node.get("name")
            or node.get("title")
            or node.get("productName")
            or node.get("displayName")
            or ""
        ).strip()
        raw_url = str(node.get("url") or node.get("productUrl") or node.get("link") or "").strip()
        if not raw_url and node.get("id"):
            return None

        if not title or not raw_url:
            return None

        url = self._normalize_product_url(raw_url)
        if not url or "-p-" not in url:
            return None

        price_display = None
        extracted = None
        for key in ("sellingPrice", "discountedPrice", "price", "salePrice"):
            value = node.get(key)
            if isinstance(value, dict):
                value = value.get("value") or value.get("amount")
            if value is not None:
                try:
                    extracted = float(value)
                    price_display = f"{extracted:.2f} TL"
                    break
                except (TypeError, ValueError):
                    pass

        if extracted is None:
            for key in ("priceText", "salePriceText", "discountedPriceText"):
                text = node.get(key)
                if text:
                    extracted, _ = parse_price_display(str(text), "tr")
                    price_display = str(text)
                    break

        stock_hint = str(node.get("stockStatus", "") or "")
        if node.get("hasStock") is False or node.get("isSoldOut") is True:
            stock_hint = f"{stock_hint} hasStock=false".strip()
        elif node.get("hasStock") is True or node.get("inStock") is True:
            stock_hint = f"{stock_hint} hasStock=true".strip()

        brand = node.get("brand")
        brand_name = None
        if isinstance(brand, dict):
            brand_name = str(brand.get("name") or "").strip() or None
        elif isinstance(brand, str):
            brand_name = brand.strip() or None

        return _ParsedProduct(
            title=title,
            url=url,
            price_display=price_display,
            extracted_price=extracted,
            brand=brand_name,
            stock_hint=stock_hint,
        )

    def _extract_products_from_urls(self, html: str) -> list[_ParsedProduct]:
        found: list[_ParsedProduct] = []
        seen: set[str] = set()
        for match in re.finditer(
            r'href="(/[^"]+-p-\d+[^"]*)"|href="(https://www\.trendyol\.com/[^"]+-p-\d+[^"]*)"',
            html,
        ):
            raw = match.group(1) or match.group(2)
            url = self._normalize_product_url(raw)
            if not url or url in seen:
                continue
            seen.add(url)
            title = url.rsplit("/", 1)[-1].replace("-", " ")
            found.append(_ParsedProduct(title=title, url=url))
        return found

    def _normalize_product_url(self, raw_url: str) -> str | None:
        if not raw_url:
            return None
        absolute = urljoin(TRENDYOL_ORIGIN, raw_url)
        parsed = urlparse(absolute)
        if parsed.netloc and "trendyol.com" not in parsed.netloc.lower():
            return None
        if "countryCode=AE" in absolute or parse_qs(parsed.query).get("countryCode") == ["AE"]:
            return None
        if "/en/" in parsed.path.lower():
            # Prefer TR storefront paths when possible.
            absolute = absolute.replace("/en/", "/", 1)

        path = parsed.path
        if "-p-" not in path:
            return None
        return urljoin(TRENDYOL_ORIGIN, path)

    def _to_results(
        self,
        products: list[_ParsedProduct],
        query: str,
        intent: Intent,
        parse_status: ParseStatus,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        for product in products[: self._max_results]:
            if apply_budget_filter(parse_status) and price_exceeds_budget(
                product.extracted_price,
                product.price_currency,
                intent.budget_amount,
                intent.budget_currency,
            ):
                continue
            snippet_parts = [p for p in (product.brand, product.price_display, product.stock_hint) if p]
            results.append(
                SearchResult(
                    title=product.title,
                    snippet=" · ".join(snippet_parts),
                    url=product.url,
                    domain=urlparse(product.url).netloc.lower(),
                    source_query=query,
                    source_engine="trendyol",
                    extracted_price=product.extracted_price,
                    price_currency=product.price_currency,
                    price_display=product.price_display,
                    merchant="Trendyol",
                )
            )
        return results
