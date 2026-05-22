from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shopping_search_agent.config import Settings
from shopping_search_agent.serpapi_client import SerpApiClient, SerpApiSearchError


def test_search_raises_on_json_error_field():
    settings = Settings()
    settings.serp_api_key = "test-key"
    client = SerpApiClient(settings)

    mock_response = MagicMock()
    mock_response.json.return_value = {"error": "Invalid API key."}
    mock_response.raise_for_status = MagicMock()

    with patch("shopping_search_agent.serpapi_client.call_with_retry", return_value=mock_response):
        with pytest.raises(SerpApiSearchError, match="Invalid API key"):
            client.search({"engine": "amazon", "amazon_domain": "amazon.com", "k": "shoes"})
