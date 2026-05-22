from __future__ import annotations

from unittest.mock import patch

import pytest

from shopping_search_agent.chat_app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


@patch("shopping_search_agent.chat_app.agent.run")
def test_api_chat_valid_request(mock_run, client):
    mock_run.return_value = {
        "route": "chitchat",
        "message": "I can help with product search requests.",
        "shortlist": [],
    }
    response = client.post("/api/chat", json={"query": "hello"})
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data.get("route") == "chitchat"
    assert "message" in data


def test_api_chat_invalid_input_returns_400(client):
    response = client.post("/api/chat", json={})
    assert response.status_code == 400
    data = response.get_json()
    assert data is not None
    assert "error" in data


def test_api_preferences_reset(client):
    with client.session_transaction() as sess:
        sess["session_id"] = "test-session-prefs"

    response = client.post("/api/preferences", json={"reset": True})
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data.get("ok") is True


def test_api_preferences_disable_personalization(client):
    response = client.post("/api/preferences", json={"enabled": False})
    assert response.status_code == 200
    data = response.get_json()
    assert data.get("personalization_enabled") is False

    with client.session_transaction() as sess:
        assert sess.get("personalization_enabled") is False
