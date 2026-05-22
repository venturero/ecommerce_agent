from __future__ import annotations

import re
from typing import Any

MAX_SUMMARY_LINES = 6
_TITLE_MAX_LEN = 52

# Only used when the same token appears in the user query (no invented durability claims).
_DURABILITY_QUERY_TERMS = (
    "durable",
    "durability",
    "rugged",
    "waterproof",
    "long-lasting",
    "long lasting",
    "sturdy",
    "reinforced",
)

MAX_FOLLOW_UP_CHIPS = 4

_BASE_CHIPS: list[dict[str, str]] = [
    {"label": "Cheaper", "query": "cheaper options"},
    {"label": "More durable", "query": "more durable options"},
    {"label": "Compare top 2", "query": "compare the top two"},
    {"label": "Different retailers", "query": "show options from different retailers"},
]


def default_follow_up_chips() -> list[dict[str, str]]:
    """Backward-compatible alias; prefer ``build_follow_up_chips``."""
    return [dict(chip) for chip in _BASE_CHIPS]


def _short_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(title).strip())
    if len(cleaned) <= _TITLE_MAX_LEN:
        return cleaned
    return cleaned[: _TITLE_MAX_LEN - 3].rstrip() + "..."


def _haystack(item: dict[str, Any]) -> str:
    parts = [
        item.get("title"),
        item.get("explanation"),
        item.get("snippet"),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _terms_in_haystack(haystack: str, terms: list[str]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        token = term.strip().lower()
        if token and token in haystack:
            hits.append(term.strip())
    return hits


def _listed_price(item: dict[str, Any]) -> str | None:
    price = item.get("price")
    if price:
        return str(price).strip()
    amount = item.get("extracted_price")
    currency = item.get("price_currency")
    if amount is not None and currency:
        return f"{amount} {currency}"
    if amount is not None:
        return str(amount)
    return None


def _price_amount(item: dict[str, Any]) -> float | None:
    value = item.get("extracted_price")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_decision_summary(response: dict[str, Any]) -> list[str]:
    """Deterministic 5–6 line memo from shortlist + constraints only."""
    if response.get("route") != "shopping":
        return []

    items = list(response.get("shortlist") or [])
    if len(items) < 2:
        return []

    top = items[:3]
    constraints = response.get("constraints") or {}
    query = str(response.get("query") or "").lower()
    must_have = [str(t).strip() for t in constraints.get("must_have") or [] if str(t).strip()]
    product_type = str(constraints.get("product_type") or "").strip()

    durability_terms = [t for t in _DURABILITY_QUERY_TERMS if t in query]

    lines: list[str] = []

    # --- "Better if X" lines (max 2), only with explicit listing/query signals ---
    for term in must_have:
        if len(lines) >= 2:
            break
        matches = [it for it in top if term.lower() in _haystack(it)]
        if matches:
            pick = matches[0]
            lines.append(
                f"Better if you need {term}: {_short_title(pick.get('title', 'Option'))} "
                f"({pick.get('domain', '')})"
            )

    if product_type and len(lines) < 2:
        matches = [it for it in top if product_type.lower() in _haystack(it)]
        if matches:
            pick = matches[0]
            if not any(product_type.lower() in line.lower() for line in lines):
                lines.append(
                    f"Better if {product_type} fit matters: {_short_title(pick.get('title', 'Option'))} "
                    f"({pick.get('domain', '')})"
                )

    if durability_terms and len(lines) < 2:
        term = durability_terms[0]
        matches = [it for it in top if term in _haystack(it)]
        if matches:
            pick = matches[0]
            lines.append(
                f"Better if {term} matters: {_short_title(pick.get('title', 'Option'))} "
                f"({pick.get('domain', '')})"
            )

    priced: list[tuple[dict[str, Any], float]] = []
    for item in top:
        amount = _price_amount(item)
        if amount is not None:
            priced.append((item, amount))
    if len(priced) >= 2 and len(lines) < 2:
        priced.sort(key=lambda pair: pair[1])
        low_item, low_amount = priced[0]
        high_item, high_amount = priced[-1]
        if low_item is not high_item:
            low_label = _listed_price(low_item) or str(low_amount)
            lines.append(
                f"Better if lower listed price: {_short_title(low_item.get('title', 'Option'))} "
                f"({low_label})"
            )
            if len(lines) < 2:
                high_label = _listed_price(high_item) or str(high_amount)
                lines.append(
                    f"Better if you skip the lowest price: {_short_title(high_item.get('title', 'Option'))} "
                    f"({high_label})"
                )

    domains = [str(it.get("domain") or "").strip() for it in top]
    if len({d for d in domains if d}) >= 2 and len(lines) < 2:
        seen: set[str] = set()
        for item, domain in zip(top, domains):
            if not domain or domain in seen:
                continue
            seen.add(domain)
            lines.append(
                f"Better if you prefer {domain}: {_short_title(item.get('title', 'Option'))}"
            )
            if len(lines) >= 2:
                break

    # --- Key trade-off (top 2), only explicit differences ---
    trade_off = ""
    first, second = top[0], top[1]
    h1, h2 = _haystack(first), _haystack(second)
    only_1 = [t for t in _terms_in_haystack(h1, must_have) if t not in _terms_in_haystack(h2, must_have)]
    only_2 = [t for t in _terms_in_haystack(h2, must_have) if t not in _terms_in_haystack(h1, must_have)]
    if only_1 and only_2:
        trade_off = (
            f"Key trade-off: {_short_title(first.get('title', 'Option'))} "
            f"({only_1[0]} in listing) vs {_short_title(second.get('title', 'Option'))} "
            f"({only_2[0]} in listing)"
        )
    else:
        p1, p2 = _price_amount(first), _price_amount(second)
        if p1 is not None and p2 is not None and p1 != p2:
            cheaper, pricier = (first, second) if p1 < p2 else (second, first)
            trade_off = (
                f"Key trade-off: {_short_title(cheaper.get('title', 'Option'))} "
                f"(lower listed price) vs {_short_title(pricier.get('title', 'Option'))} "
                f"(higher listed price)"
            )
        elif domains[0] and domains[1] and domains[0] != domains[1]:
            trade_off = (
                f"Key trade-off: {_short_title(first.get('title', 'Option'))} ({domains[0]}) vs "
                f"{_short_title(second.get('title', 'Option'))} ({domains[1]})"
            )

    if trade_off:
        lines.append(trade_off)

    # --- Conditional recommendation (never absolute "best product") ---
    if lines and trade_off:
        lines.append(
            "Recommendation: compare the options above; pick based on whether price, "
            "retailer, or must-have fit matters more for you."
        )
    elif lines:
        lead = _short_title(top[0].get("title", "the first option"))
        lines.append(
            f"Recommendation: {lead} is a stronger option for intent match; "
            f"others may be better if your priority shifts."
        )
    elif trade_off:
        lines.append(
            "Recommendation: use the trade-off above to choose; verify price and stock on each retailer page."
        )

    return lines[:MAX_SUMMARY_LINES]


def _intent_bullets(constraints: dict[str, Any], query: str) -> list[str]:
    bullets: list[str] = []
    product_type = str(constraints.get("product_type") or "").strip()
    if product_type:
        bullets.append(f"Product: {product_type}")
    must_have = [str(t).strip() for t in constraints.get("must_have") or [] if str(t).strip()]
    if must_have:
        bullets.append(f"Must-have: {', '.join(must_have)}")
    nice = [str(t).strip() for t in constraints.get("nice_to_have") or [] if str(t).strip()]
    if nice:
        bullets.append(f"Nice-to-have: {', '.join(nice)}")
    brands = [str(t).strip() for t in constraints.get("brand_include") or [] if str(t).strip()]
    if brands:
        bullets.append(f"Brands: {', '.join(brands)}")
    retailers = [str(t).strip() for t in constraints.get("retailer_include") or [] if str(t).strip()]
    if retailers:
        bullets.append(f"Retailers: {', '.join(retailers)}")
    budget = constraints.get("budget")
    budget_amount = constraints.get("budget_amount")
    budget_currency = constraints.get("budget_currency")
    if budget:
        bullets.append(f"Budget: {budget}")
    elif budget_amount is not None and budget_currency:
        bullets.append(f"Budget: {budget_amount} {budget_currency}")
    if not bullets and query.strip():
        bullets.append("Parsed from your message (see request above).")
    return bullets


def _option_tradeoff_notes(item: dict[str, Any], must_have: list[str]) -> list[str]:
    """Pros/cons style notes only from listing fields — no invented claims."""
    notes: list[str] = []
    haystack = _haystack(item)
    matched = _terms_in_haystack(haystack, must_have)
    if matched:
        notes.append(f"Matches must-have: {', '.join(matched)}")
    price = _listed_price(item)
    if price:
        notes.append(f"Listed price: {price}")
    explanation = str(item.get("explanation") or "").strip()
    if explanation:
        notes.append(f"Relevance note: {explanation}")
    elif str(item.get("snippet") or "").strip():
        snippet = re.sub(r"\s+", " ", str(item.get("snippet")))[:140].strip()
        notes.append(f"Listing snippet: {snippet}")
    return notes


def build_shareable_markdown(response: dict[str, Any]) -> str:
    """Copy/download-ready memo from session response JSON (no LLM)."""
    if response.get("route") != "shopping":
        return ""

    query = str(response.get("query") or "").strip()
    constraints = response.get("constraints") or {}
    must_have = [str(t).strip() for t in constraints.get("must_have") or [] if str(t).strip()]
    items = list(response.get("shortlist") or [])
    if not query and not items:
        return ""

    lines: list[str] = [
        "# Shopping decision memo",
        "",
        "## Your request",
        query or "(no query recorded)",
        "",
        "## Intent",
    ]
    intent_lines = _intent_bullets(constraints, query)
    lines.extend(f"- {row}" for row in intent_lines)

    lines.extend(["", "## Options (shortlist)"])
    if not items:
        lines.append("- No product links in this response.")
    else:
        for idx, item in enumerate(items[:5], start=1):
            title = _short_title(str(item.get("title") or "Untitled"))
            domain = str(item.get("domain") or "").strip()
            url = str(item.get("url") or "").strip()
            header = f"{idx}. **{title}**"
            if domain:
                header += f" ({domain})"
            if url:
                lines.append(f"{header} — {url}")
            else:
                lines.append(header)
            for note in _option_tradeoff_notes(item, must_have):
                lines.append(f"   - {note}")

    summary = build_decision_summary(response)
    lines.extend(["", "## Trade-offs & recommendation"])
    if summary:
        lines.extend(f"- {row}" for row in summary)
    elif len(items) >= 2:
        lines.append("- Compare options above; verify price and stock on each retailer page.")
    else:
        lines.append("- Add more options or refine your request to surface trade-offs.")

    disclaimer = str(response.get("disclaimer") or "").strip()
    if disclaimer:
        lines.extend(["", "---", f"*{disclaimer}*"])

    return "\n".join(lines).strip()


def build_follow_up_chips(response: dict[str, Any]) -> list[dict[str, str]]:
    """Up to four decision actions tailored to the current shortlist and constraints."""
    if response.get("route") != "shopping":
        return []

    items = list(response.get("shortlist") or [])
    if not items:
        return []

    constraints = response.get("constraints") or {}
    query = str(response.get("query") or "").lower()
    product_type = str(constraints.get("product_type") or "products").strip() or "products"
    must_have = [str(t).strip() for t in constraints.get("must_have") or [] if str(t).strip()]
    retailer_include = [
        str(t).strip() for t in constraints.get("retailer_include") or [] if str(t).strip()
    ]

    chips: list[dict[str, str]] = []
    seen_queries: set[str] = set()

    def add(label: str, q: str) -> None:
        key = q.strip().lower()
        if not key or key in seen_queries or len(chips) >= MAX_FOLLOW_UP_CHIPS:
            return
        seen_queries.add(key)
        chips.append({"label": label, "query": q})

    if len(items) >= 2:
        add("Compare top 2", "compare the top two")

    has_prices = any(_price_amount(item) is not None or item.get("price") for item in items)
    if has_prices or constraints.get("budget") or constraints.get("budget_amount") is not None:
        add("Cheaper", f"cheaper {product_type} options")

    durability_terms = [t for t in _DURABILITY_QUERY_TERMS if t in query]
    if durability_terms:
        add("More durable", f"more durable {product_type} options")
    elif must_have:
        add(f"More {must_have[0]}", f"{must_have[0]} {product_type} options")

    domains = {str(item.get("domain") or "").strip() for item in items if item.get("domain")}
    if len(domains) >= 2:
        add("Different retailers", "show options from different retailers")
    elif retailer_include:
        add(f"More on {retailer_include[0]}", f"show me more on {retailer_include[0]}")

    for base in _BASE_CHIPS:
        if len(chips) >= MAX_FOLLOW_UP_CHIPS:
            break
        add(str(base["label"]), str(base["query"]))

    return chips[:MAX_FOLLOW_UP_CHIPS]
