from __future__ import annotations

import logging
from typing import Any

from .event_db import (
    clear_session_preferences,
    get_session_preferences,
    increment_preference,
    insert_event,
    init_db,
    normalize_domain,
)
from .limits import MAX_MESSAGE_TEXT_LENGTH

logger = logging.getLogger(__name__)

PREFERENCE_BOOST_PER_CLICK = 0.05
MAX_PREFERENCE_CLICKS_FOR_BOOST = 5
MAX_PREFERENCE_BOOST = MAX_PREFERENCE_CLICKS_FOR_BOOST * PREFERENCE_BOOST_PER_CLICK

_VALID_EVENT_TYPES = frozenset({"product_click", "message_send", "impression"})

_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "product_click": ("url", "domain", "position"),
    "message_send": ("message_text",),
    "impression": ("url", "domain", "position"),
}


def _configure_event_logger() -> None:
    if getattr(_configure_event_logger, "_done", False):
        return
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    _configure_event_logger._done = True  # type: ignore[attr-defined]


_configure_event_logger()
init_db()


def effective_click_count(raw_clicks: int) -> int:
    return min(max(raw_clicks, 0), MAX_PREFERENCE_CLICKS_FOR_BOOST)


def record_click_preference(session_id: str, domain: str) -> None:
    key = normalize_domain(domain)
    if not key:
        return
    increment_preference(session_id, key)


def reset_session_preferences(session_id: str) -> None:
    clear_session_preferences(session_id)


def preference_boost(session_id: str | None, domain: str, preferences: dict[str, int] | None = None) -> float:
    if not session_id:
        return 0.0
    counts = preferences if preferences is not None else get_session_preferences(session_id)
    raw = counts.get(normalize_domain(domain), 0)
    return effective_click_count(raw) * PREFERENCE_BOOST_PER_CLICK


def record_event(payload: dict[str, Any]) -> str | None:
    event_type = str(payload.get("event_type", "")).strip().lower()
    if event_type not in _VALID_EVENT_TYPES:
        return f"event_type must be one of: {', '.join(sorted(_VALID_EVENT_TYPES))}"

    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        return "session_id is required"

    for field in _REQUIRED_FIELDS[event_type]:
        if field not in payload:
            return f"{field} is required for {event_type}"

    if event_type in {"product_click", "impression"}:
        try:
            position = int(payload["position"])
        except (TypeError, ValueError):
            return "position must be an integer"
        if position < 1:
            return "position must be >= 1"
        url = str(payload["url"])
        domain = str(payload["domain"])
        message_text = None
    else:
        position = None
        url = None
        domain = None
        message_text = str(payload["message_text"])
        if len(message_text) > MAX_MESSAGE_TEXT_LENGTH:
            return "message_text is too long"

    event_id = insert_event(
        event_type=event_type,
        session_id=session_id,
        url=url,
        domain=domain,
        position=position,
        message_text=message_text,
    )

    if event_type == "product_click":
        record_click_preference(session_id, str(payload["domain"]))

    log_event = {
        "id": event_id,
        "event_type": event_type,
        "session_id": session_id,
        "url": url,
        "domain": domain,
        "position": position,
        "message_text": message_text,
    }
    logger.info(f"track_event {log_event}")
    return None
