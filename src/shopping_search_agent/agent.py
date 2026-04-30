from __future__ import annotations

from .config import Settings
from .explanation import ExplanationLayer
from .intent_parser import IntentParser
from .llm import build_llm_client
from .query_generator import QueryGenerator
from .ranking import RankingFilter
from .router import SemanticRouter
from .search import SerpApiSearchRetriever


class ShoppingSearchAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llm = build_llm_client(settings)
        self._router = SemanticRouter(self._llm)
        self._intent_parser = IntentParser(self._llm)
        self._query_generator = QueryGenerator()
        self._retriever = SerpApiSearchRetriever(settings)
        self._ranker = RankingFilter()
        self._explainer = ExplanationLayer(self._llm)

    def run(self, user_query: str) -> dict:
        route = self._router.route(user_query)
        if route != "shopping":
            return {
                "understood_intent": {
                    "original_query": user_query,
                    "route": route,
                    "message": "Query is not shopping-related, so the shopping agent did not run.",
                },
                "recommended_links": [],
                "disclaimer": "No shopping links returned for non-shopping input.",
            }

        intent = self._intent_parser.parse(user_query)
        generated_queries = self._query_generator.generate(intent)
        search_results = self._retriever.search_many(generated_queries)
        ranked = self._ranker.rank(intent, search_results, top_k=self._settings.max_recommended_links)
        explained = self._explainer.enrich(intent, ranked)
        if len(explained) < self._settings.min_recommended_links:
            explained = explained[: self._settings.min_recommended_links]

        return {
            "understood_intent": {
                "original_query": intent.original_query,
                "product_type": intent.product_type,
                "attributes": intent.attributes,
                "budget": intent.budget,
                "usage": intent.usage,
                "generated_search_queries": generated_queries,
            },
            "recommended_links": [
                {
                    "title": item.title,
                    "url": item.url,
                    "domain": item.domain,
                    "explanation": item.explanation,
                }
                for item in explained
            ],
            "disclaimer": (
                "Prices, stock, shipping, and campaign details can change. "
                "Please verify the latest information directly on the target site."
            ),
        }
