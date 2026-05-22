from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from shopping_search_agent.config import Settings
from shopping_search_agent.models import Intent, SearchResult
from shopping_search_agent.search import MultiEngineRetriever
from shopping_search_agent.serpapi_client import SerpApiSearchError


def test_search_all_continues_when_amazon_serpapi_fails():
    settings = Settings()
    settings.use_amazon_search = True
    settings.use_trendyol_native = True
    settings.use_trendyol_serpapi_fallback = False

    retriever = MultiEngineRetriever(settings)
    retriever._search_amazon = MagicMock(  # type: ignore[method-assign]
        side_effect=SerpApiSearchError("Amazon engine quota exceeded")
    )
    retriever._trendyol.search = MagicMock(  # type: ignore[method-assign]
        return_value=[
            SearchResult(
                title="Beyaz Kolsuz Tişört",
                snippet="pamuk",
                url="https://www.trendyol.com/x-p-1",
                domain="trendyol.com",
                source_query="beyaz erkek tshirt",
                source_engine="trendyol",
            )
        ]
    )

    intent = Intent(original_query="white tshirt", product_type="tshirt")
    results = retriever.search_all(
        intent,
        primary_query="white tshirt",
        trendyol_queries=["beyaz erkek tshirt"],
        parse_status="ok",
    )
    assert len(results) == 1
    assert results[0].domain == "trendyol.com"


def test_search_all_raises_when_all_serp_paths_fail():
    settings = Settings()
    settings.use_amazon_search = True
    settings.use_trendyol_native = False
    settings.use_trendyol_serpapi_fallback = False

    retriever = MultiEngineRetriever(settings)
    retriever._search_amazon = MagicMock(  # type: ignore[method-assign]
        side_effect=SerpApiSearchError("Invalid API key")
    )

    intent = Intent(original_query="shoes", product_type="shoes")
    with pytest.raises(SerpApiSearchError):
        retriever.search_all(
            intent,
            primary_query="shoes",
            trendyol_queries=[],
            parse_status="ok",
        )
