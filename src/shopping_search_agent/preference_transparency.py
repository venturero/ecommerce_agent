from __future__ import annotations

from .event_db import normalize_domain
from .event_tracking import (
    MAX_PREFERENCE_CLICKS_FOR_BOOST,
    PREFERENCE_BOOST_PER_CLICK,
    effective_click_count,
)
from .models import Intent, SearchResult


def capped_preference_boost(
    domain: str,
    preference_counts: dict[str, int],
) -> tuple[float, list[str]]:
    """Return dampened boost and human-readable lines tied to stored click counts."""
    key = normalize_domain(domain)
    raw = preference_counts.get(key, 0)
    if raw <= 0:
        return 0.0, []

    effective = effective_click_count(raw)
    boost = round(effective * PREFERENCE_BOOST_PER_CLICK, 4)
    host = key or domain
    if raw > effective:
        return boost, [
            (
                f"Boosted +{boost:.2f} from {effective} recent click(s) on {host} "
                f"(personalization capped at {MAX_PREFERENCE_CLICKS_FOR_BOOST} clicks; "
                f"you have {raw} total in this session)."
            )
        ]
    click_word = "click" if raw == 1 else "clicks"
    return boost, [
        f"Boosted +{boost:.2f} because you clicked {host} {raw} {click_word} earlier in this session."
    ]


def build_base_ranking_signals(
    intent: Intent,
    item: SearchResult,
    *,
    domain_weight: float,
    engine_weight: float,
    retailer_matched: bool,
) -> list[str]:
    lines: list[str] = []
    if intent.product_type:
        lines.append(f"Matched your request for {intent.product_type}.")
    if intent.must_have:
        lines.append(f"Checked must-have terms: {', '.join(intent.must_have)}.")
    if retailer_matched and intent.retailer_include:
        lines.append(
            f"From a retailer you asked for ({', '.join(intent.retailer_include)})."
        )
    if domain_weight > 1.05:
        lines.append(f"Trusted store weight applied for {item.domain}.")
    if engine_weight > 1.1:
        lines.append(f"Source engine preference ({item.source_engine}).")
    if item.in_stock is True:
        lines.append("In-stock signal from metadata.")
    return lines


def build_why_seeing_this(
    base_signals: list[str],
    preference_signals: list[str],
    *,
    personalization_enabled: bool,
) -> str:
    parts = list(base_signals)
    if not personalization_enabled:
        parts.append("Personalization is off for this session (click history ignored).")
    elif preference_signals:
        parts.extend(preference_signals)
    elif personalization_enabled:
        parts.append("No personalization boost for this store yet.")
    return " ".join(parts).strip()
