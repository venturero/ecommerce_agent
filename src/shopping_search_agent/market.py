from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

DEFAULT_USD_TO_TRY = 45.54

DEFAULT_COUNTRY_CODE = "tr"
DEFAULT_LANGUAGE = "tr"

TRUSTED_DOMAINS: dict[str, list[str]] = {
    "tr": [
        "amazon.com.tr",
        "trendyol.com",
        "hepsiburada.com",
        "n11.com",
        "mediamarkt.com.tr",
        "nike.com",
    ],
    "us": [
        "amazon.com",
        "trendyol.com",
        "hepsiburada.com",
        "n11.com",
        "nike.com",
        "adidas.com",
    ],
}

TRUSTED_MERCHANT_NAMES = (
    "trendyol",
    "hepsiburada",
    "n11",
    "amazon",
    "mediamarkt",
    "nike",
    "adidas",
)

@dataclass(frozen=True)
class MarketContext:
    country_code: str
    language: str


def usd_to_try_rate() -> float:
    raw = os.getenv("USD_TO_TRY_RATE", "")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return DEFAULT_USD_TO_TRY


def _clean_code(value: object) -> str:
    if value is None:
        return ""
    text = str(value).lower().strip()
    return "" if not text or text == "null" else text


def normalize_market(country_code: object, language: object) -> tuple[str, str]:
    """Defaults only when LLM omits values (no country/language tables in code)."""
    code = _clean_code(country_code) or DEFAULT_COUNTRY_CODE
    lang = _clean_code(language) or DEFAULT_LANGUAGE
    return code, lang


def market_for_search(intent: object) -> MarketContext:
    """Runtime market for retrieval/ranking; not stored as parsed constraints."""
    country = getattr(intent, "country_code", None) or DEFAULT_COUNTRY_CODE
    language = getattr(intent, "language", None) or DEFAULT_LANGUAGE
    return MarketContext(country_code=country, language=language)


def trusted_domains_for(market: MarketContext) -> list[str]:
    return TRUSTED_DOMAINS.get(market.country_code, TRUSTED_DOMAINS["us"])


def amazon_domain_for(market: MarketContext) -> str:
    return "amazon.com.tr" if market.country_code == "tr" else "amazon.com"


def parse_amount_string(raw: str, currency_hint: str | None) -> float:
    cleaned = raw.strip()
    if currency_hint == "TRY" and "," in cleaned and "." in cleaned:
        # e.g. 9.900,00
        whole, frac = cleaned.rsplit(",", 1)
        whole_digits = whole.replace(".", "")
        return float(f"{whole_digits}.{frac}")
    if currency_hint == "TRY" and "," in cleaned:
        whole, frac = cleaned.split(",", 1)
        return float(f"{whole.replace('.', '')}.{frac}")
    return float(cleaned.replace(",", ""))


def parse_price_display(price: str | None, country_code: str) -> tuple[float | None, str | None]:
    if not price:
        return None, None
    text = price.strip()
    lowered = text.lower()
    if "₺" in text or re.search(r"\btl\b|\btry\b", lowered):
        match = re.search(r"([\d.,]+)", text)
        if match:
            return parse_amount_string(match.group(1), "TRY"), "TRY"
    if "$" in text or "usd" in lowered:
        match = re.search(r"([\d.,]+)", text)
        if match:
            return parse_amount_string(match.group(1), "USD"), "USD"
    if "€" in text or "eur" in lowered:
        match = re.search(r"([\d.,]+)", text)
        if match:
            return parse_amount_string(match.group(1), "EUR"), "EUR"
    match = re.search(r"([\d.,]+)", text)
    if not match:
        return None, None
    currency = "TRY" if country_code == "tr" else "USD"
    return parse_amount_string(match.group(1), currency), currency


def budget_limit_try(intent_budget_amount: float | None, intent_budget_currency: str | None) -> int | None:
    if intent_budget_amount is None:
        return None
    currency = (intent_budget_currency or "USD").upper()
    if currency == "TRY":
        return int(intent_budget_amount)
    return int(intent_budget_amount * usd_to_try_rate())


def budget_limit_usd(intent_budget_amount: float | None, intent_budget_currency: str | None) -> float | None:
    if intent_budget_amount is None:
        return None
    currency = (intent_budget_currency or "USD").upper()
    if currency == "USD":
        return intent_budget_amount
    if currency == "TRY":
        return intent_budget_amount / usd_to_try_rate()
    if currency == "EUR":
        return intent_budget_amount * 1.08
    return intent_budget_amount


def to_usd(amount: float, currency: str) -> float:
    code = currency.upper()
    if code == "USD":
        return amount
    if code == "TRY":
        return amount / usd_to_try_rate()
    if code == "EUR":
        return amount * 1.08
    return amount


def price_exceeds_budget(
    amount: float | None,
    currency: str | None,
    budget_amount: float | None,
    budget_currency: str | None,
) -> bool:
    if amount is None or budget_amount is None:
        return False
    budget_usd = budget_limit_usd(budget_amount, budget_currency)
    if budget_usd is None:
        return False
    price_usd = to_usd(amount, currency or "USD")
    return price_usd > budget_usd * 1.05


def extract_prices(text: str) -> list[tuple[float, str]]:
    lowered = text.lower()
    prices: list[tuple[float, str]] = []
    for match in re.finditer(
        r"(?:₺|tl|try)\s*([\d.,]+)|([\d.,]+)\s*(?:₺|tl|try)|"
        r"(?:\$|usd)\s*([\d.,]+)|([\d.,]+)\s*(?:\$|usd)|"
        r"(?:€|eur)\s*([\d.,]+)|([\d.,]+)\s*(?:€|eur)",
        lowered,
    ):
        groups = match.groups()
        if groups[0] or groups[1]:
            amount = groups[0] or groups[1]
            prices.append((parse_amount_string(amount, "TRY"), "TRY"))
        elif groups[2] or groups[3]:
            amount = groups[2] or groups[3]
            prices.append((parse_amount_string(amount, "USD"), "USD"))
        elif groups[4] or groups[5]:
            amount = groups[4] or groups[5]
            prices.append((parse_amount_string(amount, "EUR"), "EUR"))
    return prices


def exceeds_budget(
    text: str,
    budget_amount: float | None,
    budget_currency: str | None,
) -> bool:
    if budget_amount is None:
        return False
    prices = extract_prices(text)
    for amount, currency in prices:
        if price_exceeds_budget(amount, currency, budget_amount, budget_currency):
            return True
    return False


def domain_matches_trusted(domain: str, market: MarketContext) -> bool:
    host = domain.lower().lstrip("www.")
    for trusted in trusted_domains_for(market):
        if host == trusted or host.endswith(f".{trusted}") or host.endswith(trusted):
            return True
    return False


def url_matches_trusted_retailer(url: str, market: MarketContext) -> bool:
    if not url or "google.com" in url:
        return False
    host = urlparse(url).netloc.lower()
    return domain_matches_trusted(host, market)


def merchant_matches_trusted(name: str | None) -> bool:
    if not name:
        return False
    lowered = name.lower()
    return any(token in lowered for token in TRUSTED_MERCHANT_NAMES)


def is_product_page(url: str) -> bool:
    path = urlparse(url).path.lower()
    if re.search(r"/dp/[a-z0-9]{8,}", path) or "/gp/product/" in path:
        return True
    if re.search(r"-p-\d+", path):
        return True
    if re.search(r"nike\.com/(?:tr/)?t/", url.lower()):
        return True
    if re.search(r"hepsiburada\.com/.+-p-\w+", url.lower()):
        return True
    return False


def is_search_or_category_page(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    if "/s?" in url.lower() or path.rstrip("/") == "/s":
        if "k=" in query or path == "/s":
            return True
    if re.search(r"nike\.com/(?:[a-z]{2}/)?w/", url.lower()):
        return True
    if "hepsiburada.com" in parsed.netloc and ("-xc-" in path or "-c-" in path) and "-p-" not in path:
        return True
    if "trendyol.com" in parsed.netloc and "-p-" not in path and any(
        token in path for token in ("/sr", "/s/", "/c/", "/brand/")
    ):
        return True
    if path.endswith("/s") or "/search" in path:
        return True
    return False


def locale_url_multiplier(url: str, market: MarketContext) -> float:
    if market.country_code != "tr":
        return 1.0

    lowered = url.lower()
    host = urlparse(url).netloc.lower()
    params = parse_qs(urlparse(url).query)

    if "countrycode=ae" in lowered.replace("_", "") or params.get("countryCode") == ["AE"]:
        return 0.15
    if host.endswith("amazon.com") and not host.endswith("amazon.com.tr"):
        return 0.45
    if host.endswith("amazon.com.tr"):
        return 1.35
    if "trendyol.com/tr/" in lowered:
        return 1.35
    if "trendyol.com/en/" in lowered:
        return 0.85
    if host.endswith("trendyol.com") and "countrycode" not in lowered:
        return 1.15
    if "nike.com/tr/" in lowered:
        return 1.25
    if "nike.com" in host and "/w/" in lowered:
        return 0.4
    return 1.0


def is_allowed_retailer_domain(domain: str, country_code: str) -> bool:
    host = domain.lower().lstrip("www.")
    if "trendyol.com" in host:
        return True
    if country_code == "tr":
        return host.endswith("amazon.com.tr")
    return host.endswith("amazon.com") or host.endswith("amazon.com.tr")


def registrable_domain(host: str) -> str:
    host = host.lower().lstrip("www.")
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("com", "co"):
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host
