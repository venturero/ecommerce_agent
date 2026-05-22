from __future__ import annotations

from .config import Settings
from .explanation import ExplanationLayer
from .intent_parser import IntentParser
from .llm import build_llm_client
from .public_response import NON_SHOPPING_DISCLAIMER, to_public_response
from .query_generator import QueryGenerator
from .ranking import RankingFilter
from .relevance_filter import RelevanceFilter
from .router import SemanticRouter
from .search import MultiEngineRetriever
from .stock_checker import StockChecker


class ShoppingSearchAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llm = build_llm_client(settings)
        self._router = SemanticRouter(self._llm)
        self._intent_parser = IntentParser(self._llm)
        self._query_generator = QueryGenerator()
        self._retriever = MultiEngineRetriever(settings)
        self._stock = StockChecker(self._llm)
        self._relevance = RelevanceFilter(self._llm, settings)
        self._ranker = RankingFilter()
        self._explainer = ExplanationLayer(self._llm)

    def run(
        self,
        user_query: str,
        session_id: str | None = None,
        *,
        personalization_enabled: bool = True,
    ) -> dict:
        route = self._router.route(user_query)
        if route != "shopping":
            return to_public_response(
                route=route,
                query=user_query,
                message="Query is not shopping-related, so the shopping agent did not run.",
                disclaimer=NON_SHOPPING_DISCLAIMER,
            )

        intent, parse_meta = self._intent_parser.parse(user_query)
        primary_query = self._query_generator.primary_query(intent, parse_meta)
        trendyol_queries = self._query_generator.trendyol_queries(intent, parse_meta)

        search_results = self._retriever.search_all(
            intent,
            primary_query=primary_query,
            trendyol_queries=trendyol_queries,
            parse_status=parse_meta.status,
            session_id=session_id,
        )
        search_results = self._stock.annotate(search_results)
        search_results, parse_meta = self._relevance.filter(intent, search_results, parse_meta)
        ranked = self._ranker.rank(
            intent,
            search_results,
            top_k=self._settings.max_recommended_links,
            parse_meta=parse_meta,
            session_id=session_id,
            personalization_enabled=personalization_enabled,
        )
        explained = self._explainer.enrich(intent, ranked)

        message = _build_agent_message(parse_meta)

        return to_public_response(
            route="shopping",
            query=user_query,
            intent=intent,
            parse_meta=parse_meta,
            shortlist=explained,
            message=message,
        )


def _build_agent_message(parse_meta) -> str | None:
    budget_parts: list[str] = []
    if parse_meta.budget_display:
        budget_parts.append(parse_meta.budget_display)

    if parse_meta.status == "failed":
        return (
            "I could not reliably parse your request. Showing broad results — "
            "please rephrase with product type, budget, and any brand preferences."
        )
    if "low_search_relevance" in parse_meta.warnings:
        if parse_meta.clarification_questions:
            return parse_meta.clarification_questions[0]
        return (
            "Search results did not match your request well enough to show a shortlist. "
            "Please add product type, budget, or must-have features."
        )
    if parse_meta.needs_clarification and parse_meta.clarification_questions:
        joined = " ".join(parse_meta.clarification_questions)
        detail = f"I need a bit more detail: {joined}"
        if budget_parts:
            return "\n".join([*budget_parts, detail])
        return detail
    if parse_meta.needs_clarification:
        broad = (
            "Results are based on a broad interpretation of your request. "
            "Share budget, brand, or must-have features to refine."
        )
        if budget_parts:
            return "\n".join([*budget_parts, broad])
        return broad
    if budget_parts:
        return "\n".join(budget_parts)
    return None
