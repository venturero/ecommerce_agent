from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Settings
from .intent_parser import _VAGUE_TERMS
from .llm import HeuristicLLMClient, LLMClient
from .models import Intent, ParseMeta, SearchResult

_RELEVANCE_PROMPT = (
    "Score how relevant each product listing is to the user's shopping intent (0.0 = unrelated, "
    "1.0 = clearly the right product). Use title and snippet semantics, not keyword overlap alone. "
    "Penalize wrong categories (e.g. books or vinyl when the user wants shoes). "
    'Return JSON: {"items":[{"id":0,"relevance":0.0-1.0},...]}. '
    "id must match the line id."
)

_MEDIA_WRONG_CATEGORY = (
    "vinyl",
    " lp",
    "plak",
    "kitap",
    "e-kitap",
    "audiobook",
    "hardcover",
    "paperback",
    "graphic novel",
    "roman",
    "book ",
    " books",
    " cd ",
    " dvd",
    " blu-ray",
    "album",
    "single lp",
)

_DIGITAL_WRONG_CATEGORY = (
    "gift card",
    "hediye kart",
    "subscription",
    "abonelik",
    "software license",
    "ebook only",
    "kindle edition",
)

_QUERY_PRODUCT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bshoes?\b|\bsneakers?\b|\bboots?\b|ayakkab", re.I), "shoes"),
    (re.compile(r"\bheadphones?\b|kulakl", re.I), "headphones"),
    (re.compile(r"\bphones?\b|smartphone|telefon", re.I), "phone"),
    (re.compile(r"\blaptops?\b|notebook", re.I), "laptop"),
    (re.compile(r"\btvs?\b|television", re.I), "tv"),
)


@dataclass(frozen=True)
class _ProductFamily:
    match: tuple[str, ...]
    include: tuple[str, ...]
    exclude: tuple[str, ...]


_PRODUCT_FAMILIES: tuple[_ProductFamily, ...] = (
    _ProductFamily(
        match=("shoe", "sneaker", "boot", "sandal", "slipper", "ayakkab"),
        include=(
            "shoe",
            "sneaker",
            "trainer",
            "boot",
            "sandal",
            "slipper",
            "loafer",
            "ayakkabı",
            "ayakkabi",
            "spor ayakkab",
        ),
        exclude=_MEDIA_WRONG_CATEGORY + _DIGITAL_WRONG_CATEGORY,
    ),
    _ProductFamily(
        match=("headphone", "earphone", "earbud", "kulakl"),
        include=("headphone", "earphone", "earbud", "kulaklık", "kulaklik", "airpods"),
        exclude=_MEDIA_WRONG_CATEGORY + ("phone case only", "screen protector"),
    ),
    _ProductFamily(
        match=("phone", "smartphone", "telefon"),
        include=("phone", "smartphone", "iphone", "galaxy", "telefon", "mobile"),
        exclude=_MEDIA_WRONG_CATEGORY + ("phone case", "screen protector only"),
    ),
    _ProductFamily(
        match=("laptop", "notebook", "macbook"),
        include=("laptop", "notebook", "macbook", "chromebook", "dizüstü"),
        exclude=_MEDIA_WRONG_CATEGORY,
    ),
)


class RelevanceFilter:
    def __init__(self, llm: LLMClient, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings
        self._use_llm = not isinstance(llm, HeuristicLLMClient)

    def filter(
        self,
        intent: Intent,
        results: list[SearchResult],
        parse_meta: ParseMeta,
    ) -> tuple[list[SearchResult], ParseMeta]:
        if not results:
            return results, parse_meta

        focus = _product_focus(intent)
        family = _family_for_focus(focus)
        heuristic_scores = [
            _heuristic_relevance(item, focus=focus, family=family) for item in results
        ]
        llm_scores = self._llm_relevance_scores(intent, results) if self._use_llm else {}

        kept: list[SearchResult] = []
        combined_scores: list[float] = []
        for idx, item in enumerate(results):
            h_score = heuristic_scores[idx]
            l_score = llm_scores.get(idx)
            if l_score is not None:
                combined = (0.45 * h_score) + (0.55 * l_score)
            else:
                combined = h_score
            combined_scores.append(combined)
            if combined >= self._settings.relevance_min_score:
                kept.append(item)

        vague = _is_vague_query(intent.original_query) or parse_meta.needs_clarification
        min_needed = min(3, self._settings.min_recommended_links)
        best_combined = max(combined_scores) if combined_scores else 0.0

        strong_kept = sum(1 for score in combined_scores if score >= self._settings.relevance_min_score)
        if kept and not _should_clarify_instead(
            vague=vague,
            kept_count=len(kept),
            strong_kept=strong_kept,
            min_needed=min_needed,
            best_score=best_combined,
            clarify_threshold=self._settings.relevance_clarify_max_score,
        ):
            return kept, parse_meta

        if (vague or focus) and not kept:
            return [], _clarify_for_low_relevance(parse_meta, intent, focus)

        return kept, parse_meta

    def _llm_relevance_scores(self, intent: Intent, results: list[SearchResult]) -> dict[int, float]:
        context = _intent_context(intent)
        lines = [
            f"{i}|title={r.title}|snippet={r.snippet}|url={r.url}"
            for i, r in enumerate(results)
        ]
        user_prompt = f"User intent: {context}\n\nListings:\n" + "\n".join(lines)
        try:
            data = self._llm.complete_json(_RELEVANCE_PROMPT, user_prompt)
        except Exception:
            return {}
        if not isinstance(data, dict) or data.get("raw_text"):
            return {}

        scores: dict[int, float] = {}
        for item in data.get("items") or []:
            try:
                idx = int(item["id"])
                value = float(item["relevance"])
            except (KeyError, TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(results):
                continue
            scores[idx] = max(0.0, min(1.0, value))
        return scores


def _should_clarify_instead(
    *,
    vague: bool,
    kept_count: int,
    strong_kept: int,
    min_needed: int,
    best_score: float,
    clarify_threshold: float,
) -> bool:
    if kept_count == 0:
        return True
    if not vague:
        return False
    if kept_count >= min_needed and best_score >= clarify_threshold:
        return False
    if strong_kept >= 2 and best_score >= clarify_threshold:
        return False
    if best_score >= 0.62 and kept_count >= 1:
        return False
    return kept_count < min_needed or best_score < clarify_threshold


def _clarify_for_low_relevance(parse_meta: ParseMeta, intent: Intent, focus: str | None) -> ParseMeta:
    warnings = list(parse_meta.warnings)
    if "low_search_relevance" not in warnings:
        warnings.append("low_search_relevance")

    questions = list(parse_meta.clarification_questions)
    if focus:
        detail = (
            f"I could not find reliable {focus} listings for this broad query. "
            "What style, size, or budget should I use?"
        )
    else:
        detail = "What type of product are you looking for (e.g. running shoes, boots)?"
    if detail not in questions:
        questions.insert(0, detail)
    if len(questions) < 2 and intent.budget_amount is None:
        budget_q = "What is your maximum budget (include currency)?"
        if budget_q not in questions:
            questions.append(budget_q)

    return ParseMeta(
        status=parse_meta.status if parse_meta.status != "ok" else "partial",
        confidence=min(parse_meta.confidence or 0.5, 0.4) if parse_meta.confidence else 0.4,
        needs_clarification=True,
        clarification_questions=questions[:2],
        warnings=warnings,
        errors=list(parse_meta.errors),
    )


def _product_focus(intent: Intent) -> str | None:
    if intent.product_type:
        return intent.product_type.strip()
    for pattern, label in _QUERY_PRODUCT_PATTERNS:
        if pattern.search(intent.original_query):
            return label
    return None


def _family_for_focus(focus: str | None) -> _ProductFamily | None:
    if not focus:
        return None
    lowered = focus.lower()
    for family in _PRODUCT_FAMILIES:
        if any(token in lowered for token in family.match):
            return family
    return None


def _heuristic_relevance(
    item: SearchResult,
    *,
    focus: str | None,
    family: _ProductFamily | None,
) -> float:
    title = item.title.lower()
    haystack = f"{item.title} {item.snippet} {item.merchant or ''}".lower()

    include_terms = list(family.include) if family else []
    exclude_terms = list(family.exclude) if family else list(_MEDIA_WRONG_CATEGORY)

    if focus and not family:
        include_terms.extend(_tokenize(focus))

    if _has_conflicting_category(title, haystack, include_terms, exclude_terms):
        return 0.0

    if not focus:
        return 0.55

    title_hits = sum(1 for term in include_terms if term in title)
    body_hits = sum(1 for term in include_terms if term in haystack)
    focus_hits = sum(1 for token in _tokenize(focus) if token in haystack)

    if title_hits == 0 and body_hits == 0 and focus_hits == 0:
        return 0.18

    score = 0.25
    score += min(0.45, 0.22 * title_hits)
    score += min(0.25, 0.12 * body_hits)
    score += min(0.2, 0.1 * focus_hits)
    return min(1.0, score)


def _has_conflicting_category(
    title: str,
    haystack: str,
    include_terms: list[str],
    exclude_terms: tuple[str, ...] | list[str],
) -> bool:
    if not any(term in haystack for term in exclude_terms):
        return False
    if any(term in title for term in include_terms):
        return False
    if any(term in haystack for term in include_terms):
        return False
    return True


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9ğüşıöç]+", text.lower()) if len(token) > 2]


def _is_vague_query(query: str) -> bool:
    lowered = query.lower()
    return any(term in lowered for term in _VAGUE_TERMS)


def _intent_context(intent: Intent) -> str:
    parts = [f"query={intent.original_query}"]
    if intent.product_type:
        parts.append(f"product_type={intent.product_type}")
    if intent.usage:
        parts.append(f"usage={intent.usage}")
    if intent.must_have:
        parts.append(f"must_have={', '.join(intent.must_have)}")
    if intent.attributes:
        parts.append(f"attributes={intent.attributes}")
    return " | ".join(parts)
