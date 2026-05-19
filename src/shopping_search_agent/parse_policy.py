from __future__ import annotations

from .models import Intent, ParseMeta, ParseStatus


def apply_brand_exclude_filter(parse_status: ParseStatus) -> bool:
    return parse_status == "ok"


def apply_brand_include_filter(parse_status: ParseStatus) -> bool:
    return parse_status == "ok"


def apply_must_have_filter(parse_status: ParseStatus) -> bool:
    return parse_status == "ok"


def apply_budget_filter(parse_status: ParseStatus) -> bool:
    return parse_status in ("ok", "partial")


def apply_strict_score_boosts(parse_status: ParseStatus) -> bool:
    return parse_status == "ok"
