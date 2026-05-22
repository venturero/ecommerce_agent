from __future__ import annotations

from unittest.mock import patch

import pytest

from shopping_search_agent.chat_app import _attach_ui_message, _looks_like_follow_up, app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_follow_up_detection_for_chip_queries():
    assert _looks_like_follow_up("cheaper options")
    assert _looks_like_follow_up("more durable options")
    assert _looks_like_follow_up("compare the top two")
    assert _looks_like_follow_up("show options from different retailers")


def test_attach_ui_message_adds_decision_summary_and_chips():
    response = {
        "route": "shopping",
        "query": "waterproof shoes",
        "message": "Budget note.",
        "constraints": {"product_type": "shoes", "must_have": ["waterproof"]},
        "shortlist": [
            {
                "title": "Aqua Shoe",
                "url": "https://amazon.com/a",
                "domain": "amazon.com",
                "snippet": "waterproof runner",
                "explanation": "Matches waterproof.",
            },
            {
                "title": "Dry Walk",
                "url": "https://trendyol.com/b",
                "domain": "trendyol.com",
                "snippet": "casual mesh",
                "explanation": "Lightweight option.",
            },
        ],
        "parse": {"status": "ok"},
        "disclaimer": "Verify on retailer.",
    }
    enriched = _attach_ui_message(response)
    assert enriched["ui_intro"] == "Budget note."
    assert enriched["decision_summary"]
    assert enriched["follow_up_chips"]
    assert enriched["decision_artifact_markdown"]
    assert "waterproof shoes" in enriched["decision_artifact_markdown"]
    assert "Compare top 2" in [c["label"] for c in enriched["follow_up_chips"]]


@patch("shopping_search_agent.chat_app.agent.run")
def test_api_chat_returns_day13_fields(mock_run, client):
    mock_run.return_value = {
        "route": "shopping",
        "query": "shoes",
        "message": None,
        "constraints": {"product_type": "shoes", "must_have": ["waterproof"]},
        "shortlist": [
            {
                "title": "Aqua",
                "url": "https://a.com",
                "domain": "a.com",
                "snippet": "waterproof",
            },
            {
                "title": "Lite",
                "url": "https://b.com",
                "domain": "b.com",
                "snippet": "mesh",
            },
        ],
        "parse": {"status": "ok"},
        "disclaimer": "note",
    }
    response = client.post("/api/chat", json={"query": "waterproof shoes"})
    assert response.status_code == 200
    data = response.get_json()
    assert data.get("decision_summary")
    assert data.get("follow_up_chips")
    assert data.get("decision_artifact_markdown")
    assert data.get("ui_intro")
