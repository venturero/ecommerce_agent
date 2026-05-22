from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .public_response import RESPONSE_VERSION

VALID_ROUTES = frozenset({"shopping", "chitchat"})
PARSE_STATUSES = frozenset({"ok", "partial", "failed", "skipped"})

# Phrases that suggest hallucinated social proof or ungrounded claims.
HALLUCINATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d+(\.\d+)?\s*\/\s*5\b"),
    re.compile(r"\b\d+\s*star(s)?\s*(rating|review)", re.I),
    re.compile(r"\b(verified|authentic)\s+(purchase|buyer|review)", re.I),
    re.compile(r"\bcustomers?\s+(love|rave|say)", re.I),
    re.compile(r"\b(thousands|millions)\s+of\s+reviews?", re.I),
    re.compile(r"\b(best\s*seller|#1\s+on\s+amazon)\b", re.I),
    re.compile(r"\bguaranteed\s+(delivery|in\s+stock)", re.I),
    re.compile(r"\b\d+%\s+off\b", re.I),
)

SHORTLIST_ITEM_KEYS = frozenset(
    {"title", "url", "domain", "merchant", "price", "extracted_price", "price_currency", "in_stock", "explanation"}
)


def validate_response_schema(response: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    required_top = ("version", "route", "query", "constraints", "market", "parse", "shortlist", "message", "disclaimer")
    for key in required_top:
        if key not in response:
            issues.append(f"missing_top_level_key:{key}")

    if response.get("version") != RESPONSE_VERSION:
        issues.append(f"unexpected_version:{response.get('version')}")

    route = response.get("route")
    if route not in VALID_ROUTES:
        issues.append(f"invalid_route:{route}")

    parse = response.get("parse")
    if not isinstance(parse, dict):
        issues.append("parse_not_object")
    else:
        for key in (
            "status",
            "confidence",
            "needs_clarification",
            "clarification_questions",
            "warnings",
            "errors",
        ):
            if key not in parse:
                issues.append(f"missing_parse_key:{key}")
        if parse.get("status") not in PARSE_STATUSES:
            issues.append(f"invalid_parse_status:{parse.get('status')}")

    shortlist = response.get("shortlist")
    if not isinstance(shortlist, list):
        issues.append("shortlist_not_list")
    else:
        for idx, item in enumerate(shortlist):
            if not isinstance(item, dict):
                issues.append(f"shortlist_item_{idx}_not_object")
                continue
            for key in ("title", "url", "domain"):
                if not str(item.get(key, "")).strip():
                    issues.append(f"shortlist_item_{idx}_missing_{key}")
            if item.get("url"):
                parsed = urlparse(str(item["url"]))
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    issues.append(f"shortlist_item_{idx}_invalid_url")

    return issues


def check_shortlist_bounds(
    response: dict[str, Any],
    *,
    min_links: int,
    max_links: int,
    allow_empty: bool,
    allow_clarification: bool,
) -> list[str]:
    issues: list[str] = []
    if response.get("route") != "shopping":
        return issues

    parse = response.get("parse") or {}
    shortlist = response.get("shortlist") or []
    count = len(shortlist)

    if allow_clarification and parse.get("needs_clarification"):
        return issues

    if allow_empty or parse.get("status") == "failed":
        return issues

    if "low_search_relevance" in (parse.get("warnings") or []):
        if count == 0:
            return issues
        if count < min_links:
            issues.append(f"shortlist_below_min:{count}<{min_links}")
        return issues

    if count == 0:
        issues.append("shortlist_empty")
    elif count < min_links:
        issues.append(f"shortlist_below_min:{count}<{min_links}")
    elif count > max_links:
        issues.append(f"shortlist_above_max:{count}>{max_links}")

    return issues


def check_hallucination_signals(response: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    texts: list[str] = []
    message = response.get("message")
    if message:
        texts.append(str(message))

    for item in response.get("shortlist") or []:
        explanation = item.get("explanation")
        if explanation:
            texts.append(str(explanation))

    for text in texts:
        for pattern in HALLUCINATION_PATTERNS:
            if pattern.search(text):
                issues.append(f"possible_hallucination:{pattern.pattern[:40]}")
                break

    return issues


def check_expectations(response: dict[str, Any], case: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    expected_route = case.get("expect_route")
    if expected_route and response.get("route") != expected_route:
        issues.append(f"unexpected_route:{response.get('route')}!={expected_route}")
    return issues


def run_all_checks(
    response: dict[str, Any],
    case: dict[str, Any],
    *,
    shortlist_min: int,
    shortlist_max: int,
) -> dict[str, Any]:
    issues: list[str] = []
    issues.extend(validate_response_schema(response))
    issues.extend(
        check_shortlist_bounds(
            response,
            min_links=shortlist_min,
            max_links=shortlist_max,
            allow_empty=bool(case.get("allow_empty_shortlist")),
            allow_clarification=bool(case.get("allow_clarification")),
        )
    )
    issues.extend(check_hallucination_signals(response))
    issues.extend(check_expectations(response, case))

    return {
        "passed": len(issues) == 0,
        "issues": issues,
    }
