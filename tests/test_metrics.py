from __future__ import annotations

import json

import pytest

from shopping_search_agent.event_db import (
    backup_db,
    export_db_json,
    init_db,
    insert_event,
    insert_query_request,
)
from shopping_search_agent.metrics_report import build_metrics_summary, format_report_text
from shopping_search_agent.query_metrics import classify_outcome, record_chat_request


@pytest.fixture
def metrics_db(tmp_path, monkeypatch):
    db_path = tmp_path / "metrics.db"
    monkeypatch.setenv("EVENT_DB_PATH", str(db_path))
    init_db(db_path)
    return db_path


def test_classify_outcome_empty_and_low_relevance():
    assert classify_outcome({"route": "shopping", "shortlist": []}) == "empty_shortlist"
    assert (
        classify_outcome(
            {
                "route": "shopping",
                "shortlist": [{"title": "x"}],
                "parse": {"warnings": ["low_search_relevance"]},
            }
        )
        == "low_relevance"
    )
    assert classify_outcome({"route": "chitchat", "shortlist": []}) == "chitchat"
    assert classify_outcome(None, search_failed=True) == "search_failed"


def test_build_metrics_summary_ctr_and_follow_ups(metrics_db):
    session = "sess-metrics"
    for position in (1, 2, 3):
        insert_event(
            event_type="impression",
            session_id=session,
            url=f"https://a.com/{position}",
            domain="a.com",
            position=position,
        )
    insert_event(
        event_type="product_click",
        session_id=session,
        url="https://a.com/1",
        domain="a.com",
        position=1,
    )
    insert_event(event_type="message_send", session_id=session, message_text="shoes")
    insert_event(event_type="message_send", session_id=session, message_text="cheaper")

    record_chat_request(
        session_id=session,
        query_text="shoes",
        path="agent",
        ttfb_s=0.5,
        total_s=1.2,
        outcome="ok",
        route="shopping",
        shortlist_count=3,
    )
    record_chat_request(
        session_id=session,
        query_text="cheaper",
        path="agent",
        ttfb_s=0.4,
        total_s=2.5,
        outcome="ok",
        route="shopping",
        shortlist_count=2,
        is_follow_up=True,
    )
    insert_query_request(
        session_id=session,
        query_text="broken",
        path="search_failed",
        outcome="search_failed",
        ttfb_s=0.1,
        total_s=0.2,
        error_detail="timeout",
        http_status=502,
    )

    summary = build_metrics_summary(metrics_db)
    assert summary["engagement"]["impressions"] == 3
    assert summary["engagement"]["clicks"] == 1
    assert summary["engagement"]["ctr"] == pytest.approx(1 / 3, rel=1e-3)
    assert summary["engagement"]["follow_up_sessions"] == 1
    assert summary["engagement"]["follow_up_rate_by_session"] == 1.0
    assert summary["latency"]["request_count"] == 3
    assert summary["top_failure_queries"][0]["query_text"] == "broken"
    assert "slow_queries" in summary
    text = format_report_text(summary)
    assert "CTR:" in text
    assert "broken" in text


def test_backup_and_export(metrics_db, tmp_path):
    record_chat_request(
        session_id="s1",
        query_text="test",
        path="agent",
        ttfb_s=0.1,
        total_s=0.2,
        outcome="ok",
    )
    backup_path = backup_db(tmp_path / "copy.db")
    assert backup_path.exists()

    export_path = tmp_path / "export.json"
    export_db_json(export_path)
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert len(payload["query_requests"]) == 1
    assert "events" in payload
