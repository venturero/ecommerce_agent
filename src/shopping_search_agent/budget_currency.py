from __future__ import annotations

import re
from dataclasses import dataclass

from .market import market_for_search
from .models import Intent

_CURRENCY_SYMBOLS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"₺|\btl\b|\btry\b", re.I), "TRY"),
    (re.compile(r"\$|\busd\b", re.I), "USD"),
    (re.compile(r"€|\beur\b", re.I), "EUR"),
    (re.compile(r"£|\bgbp\b", re.I), "EUR"),  # treat pound queries as EUR bucket for limits
)

_AMOUNT_PATTERNS = (
    re.compile(
        r"(?:under|below|less\s+than|max(?:imum)?|upto|up\s+to|at\s+most)\s*"
        r"([\d][\d.,]*)",
        re.I,
    ),
    re.compile(r"([\d][\d.,]*)\s*(?:tl|try|usd|eur|dollars?)\b", re.I),
    re.compile(r"budget\s*(?:of|:)?\s*([\d][\d.,]*)", re.I),
)

_CURRENCY_LABELS = {"TRY": "TL", "USD": "USD", "EUR": "EUR"}


@dataclass(frozen=True)
class BudgetResolution:
    currency_inferred: bool = False
    budget_display: str | None = None


def resolve_budget_currency(intent: Intent, user_query: str) -> BudgetResolution:
    """Fill missing budget fields and build a transparent display string."""
    query_currency = currency_from_query_text(user_query)
    amount = intent.budget_amount

    if amount is None:
        extracted_amount, trailing_currency = amount_from_query_text(user_query)
        if extracted_amount is not None:
            amount = extracted_amount
            intent.budget_amount = amount

    if intent.budget_currency is None and query_currency:
        intent.budget_currency = query_currency

    if amount is None:
        return BudgetResolution()

    inferred = False
    if not intent.budget_currency:
        intent.budget_currency = default_budget_currency(intent)
        inferred = True

    display = format_budget_display(amount, intent.budget_currency, inferred=inferred)
    if not intent.budget:
        intent.budget = display.removeprefix("Budget: ").strip()

    return BudgetResolution(
        currency_inferred=inferred,
        budget_display=display,
    )


def default_budget_currency(intent: Intent) -> str:
    market = market_for_search(intent)
    if market.country_code == "tr":
        return "TRY"
    if market.country_code == "us":
        return "USD"
    return "USD"


def format_budget_display(amount: float, currency: str, *, inferred: bool) -> str:
    code = currency.upper()
    label = _CURRENCY_LABELS.get(code, code)
    amount_text = str(int(amount)) if amount == int(amount) else f"{amount:g}"
    base = f"Budget: {amount_text} {label}"
    if inferred:
        return f"{base} (currency inferred by the system)"
    return base


def currency_from_query_text(query: str) -> str | None:
    for pattern, code in _CURRENCY_SYMBOLS:
        if pattern.search(query):
            return code
    return None


def amount_from_query_text(query: str) -> tuple[float | None, str | None]:
    trailing_currency = currency_from_query_text(query)
    for pattern in _AMOUNT_PATTERNS:
        match = pattern.search(query)
        if not match:
            continue
        try:
            amount = _parse_amount_token(match.group(1), trailing_currency)
        except ValueError:
            continue
        return amount, trailing_currency
    return None, trailing_currency


def _parse_amount_token(raw: str, currency_hint: str | None) -> float:
    cleaned = raw.strip().replace(" ", "")
    if currency_hint == "TRY" and "," in cleaned and "." in cleaned:
        whole, frac = cleaned.rsplit(",", 1)
        return float(f"{whole.replace('.', '')}.{frac}")
    if currency_hint == "TRY" and "," in cleaned:
        whole, frac = cleaned.split(",", 1)
        return float(f"{whole.replace('.', '')}.{frac}")
    return float(cleaned.replace(",", ""))


def currency_confirmation_question() -> str:
    return "Please specify your preferred currency (e.g. USD, TRY)."
