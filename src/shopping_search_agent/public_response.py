from __future__ import annotations

from .models import Intent, ParseMeta, RankedLink, Route

RESPONSE_VERSION = "1"

SHOPPING_DISCLAIMER = (
    "Prices and stock are based on retailer search metadata at query time. "
    "Please verify the latest price, availability, and shipping on the retailer page."
)
NON_SHOPPING_DISCLAIMER = "No shopping links returned for non-shopping input."


def empty_constraints() -> dict:
    return {
        "product_type": None,
        "attributes": {},
        "brand_include": [],
        "brand_exclude": [],
        "must_have": [],
        "nice_to_have": [],
        "budget": None,
        "budget_amount": None,
        "budget_currency": None,
        "usage": None,
        "retailer_include": [],
    }


def empty_market() -> dict:
    return {
        "country_code": None,
        "language": None,
        "location": None,
    }


def constraints_from_intent(intent: Intent) -> dict:
    return {
        "product_type": intent.product_type,
        "attributes": intent.attributes,
        "brand_include": intent.brand_include,
        "brand_exclude": intent.brand_exclude,
        "must_have": intent.must_have,
        "nice_to_have": intent.nice_to_have,
        "budget": intent.budget,
        "budget_amount": intent.budget_amount,
        "budget_currency": intent.budget_currency,
        "usage": intent.usage,
        "retailer_include": intent.retailer_include,
    }


def market_from_intent(intent: Intent) -> dict:
    return {
        "country_code": intent.country_code,
        "language": intent.language,
        "location": intent.location,
    }


def parse_to_dict(parse_meta: ParseMeta) -> dict:
    return {
        "status": parse_meta.status,
        "confidence": parse_meta.confidence,
        "needs_clarification": parse_meta.needs_clarification,
        "clarification_questions": list(parse_meta.clarification_questions),
        "warnings": list(parse_meta.warnings),
        "errors": list(parse_meta.errors),
        "budget_display": parse_meta.budget_display,
        "budget_currency_inferred": parse_meta.budget_currency_inferred,
    }


def shortlist_from_links(links: list[RankedLink]) -> list[dict]:
    return [
        {
            "title": item.title,
            "url": item.url,
            "domain": item.domain,
            "merchant": item.merchant,
            "price": item.price_display,
            "extracted_price": item.extracted_price,
            "price_currency": item.price_currency,
            "in_stock": item.in_stock,
            "explanation": item.explanation,
        }
        for item in links
    ]


def to_public_response(
    *,
    route: Route,
    query: str,
    intent: Intent | None = None,
    parse_meta: ParseMeta | None = None,
    shortlist: list[RankedLink] | None = None,
    message: str | None = None,
    disclaimer: str | None = None,
) -> dict:
    is_shopping = route == "shopping"

    if is_shopping and intent is not None:
        constraints = constraints_from_intent(intent)
        market = market_from_intent(intent)
    else:
        constraints = empty_constraints()
        market = empty_market()

    if parse_meta is not None:
        parse = parse_to_dict(parse_meta)
    else:
        parse = {
            "status": "skipped",
            "confidence": None,
            "needs_clarification": False,
            "clarification_questions": [],
            "warnings": [],
            "errors": [],
            "budget_display": None,
            "budget_currency_inferred": False,
        }

    return {
        "version": RESPONSE_VERSION,
        "route": route,
        "query": query,
        "constraints": constraints,
        "market": market,
        "parse": parse,
        "shortlist": shortlist_from_links(shortlist or []),
        "message": message,
        "disclaimer": disclaimer
        if disclaimer is not None
        else (SHOPPING_DISCLAIMER if is_shopping else NON_SHOPPING_DISCLAIMER),
    }
