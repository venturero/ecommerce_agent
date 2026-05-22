from __future__ import annotations

import pytest

from shopping_search_agent.event_db import get_session_preferences, increment_preference, init_db
from shopping_search_agent.event_tracking import (
    MAX_PREFERENCE_BOOST,
    MAX_PREFERENCE_CLICKS_FOR_BOOST,
    PREFERENCE_BOOST_PER_CLICK,
    effective_click_count,
    preference_boost,
    reset_session_preferences,
)
from shopping_search_agent.models import Intent, ParseMeta, SearchResult
from shopping_search_agent.preference_transparency import (
    build_why_seeing_this,
    capped_preference_boost,
)
from shopping_search_agent.ranking import RankingFilter


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_events.db"
    monkeypatch.setenv("EVENT_DB_PATH", str(db_path))
    init_db(db_path)
    return db_path


def test_effective_click_count_caps_boost():
    assert effective_click_count(0) == 0
    assert effective_click_count(3) == 3
    assert effective_click_count(99) == MAX_PREFERENCE_CLICKS_FOR_BOOST


def test_preference_boost_is_capped(temp_db):
    session_id = "sess-cap"
    domain = "amazon.com"
    for _ in range(10):
        increment_preference(session_id, domain)
    boost = preference_boost(session_id, domain)
    assert boost == pytest.approx(MAX_PREFERENCE_BOOST)
    assert boost == pytest.approx(MAX_PREFERENCE_CLICKS_FOR_BOOST * PREFERENCE_BOOST_PER_CLICK)


def test_capped_preference_boost_explains_cap():
    counts = {"amazon.com": 8}
    boost, lines = capped_preference_boost("www.amazon.com", counts)
    assert boost == pytest.approx(MAX_PREFERENCE_BOOST)
    assert lines
    assert "capped" in lines[0].lower()
    assert "8" in lines[0]


def test_reset_session_preferences_clears_clicks(temp_db):
    session_id = "sess-reset"
    increment_preference(session_id, "trendyol.com")
    assert get_session_preferences(session_id)["trendyol.com"] == 1
    reset_session_preferences(session_id)
    assert get_session_preferences(session_id) == {}


def test_ranking_attaches_why_seeing_this_with_personalization(temp_db):
    session_id = "sess-why"
    increment_preference(session_id, "amazon.com")

    intent = Intent(
        original_query="running shoes",
        product_type="running shoes",
        country_code="us",
    )
    item = SearchResult(
        title="Nike Running Shoes",
        snippet="lightweight trainers",
        url="https://www.amazon.com/dp/123",
        domain="amazon.com",
        source_query="running shoes",
        source_engine="amazon",
        in_stock=True,
    )
    parse_meta = ParseMeta(status="ok")

    ranked = RankingFilter().rank(
        intent,
        [item],
        top_k=5,
        parse_meta=parse_meta,
        session_id=session_id,
        personalization_enabled=True,
    )
    assert len(ranked) == 1
    assert ranked[0].why_seeing_this
    assert "clicked" in ranked[0].why_seeing_this.lower() or "boosted" in ranked[0].why_seeing_this.lower()


def test_ranking_ignores_clicks_when_personalization_disabled(temp_db):
    session_id = "sess-off"
    increment_preference(session_id, "amazon.com")

    intent = Intent(
        original_query="running shoes",
        product_type="running shoes",
        country_code="us",
    )
    item = SearchResult(
        title="Nike Running Shoes",
        snippet="lightweight trainers",
        url="https://www.amazon.com/dp/123",
        domain="amazon.com",
        source_query="running shoes",
        source_engine="amazon",
    )
    ranked_on = RankingFilter().rank(
        intent, [item], top_k=5, parse_meta=ParseMeta(status="ok"), session_id=session_id
    )
    ranked_off = RankingFilter().rank(
        intent,
        [item],
        top_k=5,
        parse_meta=ParseMeta(status="ok"),
        session_id=session_id,
        personalization_enabled=False,
    )
    assert ranked_on[0].score > ranked_off[0].score
    assert "personalization is off" in ranked_off[0].why_seeing_this.lower()


def test_build_why_seeing_this_merges_signals():
    text = build_why_seeing_this(
        ["Matched your request for shoes."],
        ["Boosted +0.05 because you clicked amazon.com 1 click earlier in this session."],
        personalization_enabled=True,
    )
    assert "Matched your request" in text
    assert "Boosted" in text
