from __future__ import annotations

import re

from .models import Intent

# Canonical retailer keys used across search/ranking.
_RETAILER_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\btrendyol\b", re.I), "trendyol"),
    (re.compile(r"\bamazon(?:\.com(?:\.tr)?)?\b", re.I), "amazon"),
    (re.compile(r"\bhepsiburada\b", re.I), "hepsiburada"),
    (re.compile(r"\bn11\b", re.I), "n11"),
)


def detect_retailer_preferences(text: str) -> list[str]:
    """Heuristic store detection from the raw user message."""
    lowered = text.lower()
    found: list[str] = []
    for pattern, key in _RETAILER_PATTERNS:
        if pattern.search(lowered) and key not in found:
            found.append(key)
    return found


def merge_retailer_preferences(intent: Intent, user_query: str) -> Intent:
    """Combine LLM retailer_include with regex hints from the original query."""
    from_query = detect_retailer_preferences(user_query)
    merged: list[str] = []
    for key in [*intent.retailer_include, *from_query]:
        normalized = key.strip().lower()
        if normalized and normalized not in merged:
            merged.append(normalized)
    intent.retailer_include = merged
    return intent


def prefers_retailer(intent: Intent, retailer: str) -> bool:
    if not intent.retailer_include:
        return False
    return retailer.lower() in {r.lower() for r in intent.retailer_include}


def retailer_only(intent: Intent) -> str | None:
    """When the user names exactly one store, return that key."""
    if len(intent.retailer_include) == 1:
        return intent.retailer_include[0].lower()
    return None


def domain_matches_retailer(domain: str, retailer: str) -> bool:
    host = domain.lower().lstrip("www.")
    key = retailer.lower()
    if key == "trendyol":
        return "trendyol.com" in host
    if key == "amazon":
        return host.endswith("amazon.com") or host.endswith("amazon.com.tr")
    if key == "hepsiburada":
        return "hepsiburada.com" in host
    if key == "n11":
        return host.endswith("n11.com")
    return key in host


def result_matches_retailer_preferences(item_domain: str, preferences: list[str]) -> bool:
    if not preferences:
        return True
    return any(domain_matches_retailer(item_domain, pref) for pref in preferences)
