"""Persist chat request outcomes and latency for launch metrics."""

from __future__ import annotations

from typing import Any

from .event_db import insert_query_request

_FAILURE_OUTCOMES = frozenset(
    {
        "search_failed",
        "error",
        "rate_limited",
        "session_unavailable",
        "empty_shortlist",
        "low_relevance",
    }
)


def classify_outcome(
    response: dict[str, Any] | None,
    *,
    search_failed: bool = False,
    rate_limited: bool = False,
    session_unavailable: bool = False,
    server_error: bool = False,
) -> str:
    if rate_limited:
        return "rate_limited"
    if session_unavailable:
        return "session_unavailable"
    if search_failed or server_error:
        return "search_failed" if search_failed else "error"
    if not response:
        return "error"

    route = str(response.get("route", ""))
    if route != "shopping":
        return "chitchat"

    shortlist = response.get("shortlist") or []
    if len(shortlist) == 0:
        return "empty_shortlist"

    parse_block = response.get("parse") or {}
    warnings = parse_block.get("warnings") or []
    if "low_search_relevance" in warnings:
        return "low_relevance"

    return "ok"


def is_failure_outcome(outcome: str) -> bool:
    return outcome in _FAILURE_OUTCOMES


def record_chat_request(
    *,
    session_id: str,
    query_text: str,
    path: str,
    ttfb_s: float,
    total_s: float,
    outcome: str,
    route: str = "",
    shortlist_count: int | None = None,
    http_status: int = 200,
    error_detail: str | None = None,
    is_follow_up: bool = False,
) -> int:
    preview = query_text if len(query_text) <= 500 else f"{query_text[:497]}..."
    return insert_query_request(
        session_id=session_id,
        query_text=preview,
        path=path,
        outcome=outcome,
        ttfb_s=ttfb_s,
        total_s=total_s,
        route=route or None,
        shortlist_count=shortlist_count,
        http_status=http_status,
        error_detail=error_detail,
        is_follow_up=is_follow_up,
    )
