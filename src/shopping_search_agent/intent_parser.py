from __future__ import annotations

import re

from .budget_currency import currency_confirmation_question, resolve_budget_currency
from .constraint_negation import apply_negation_heuristics
from .retailer_preference import merge_retailer_preferences
from .llm import LLMClient
from .market import normalize_market
from .models import Intent, ParseMeta, ParseStatus

_INTENT_PROMPT = (
    "Extract shopping intent as JSON. Keys: "
    "product_type(string|null), attributes(object), brand_include(array of strings), "
    "brand_exclude(array of strings), must_have(array of strings - hard requirements), "
    "nice_to_have(array of strings - soft preferences), "
    "retailer_include(array of strings - when user names a store/marketplace, e.g. trendyol, amazon), "
    "usage(string|null), location(string|null), "
    "country_code(2-letter|null), language(2-letter|null), "
    "budget_amount(number|null), budget_currency(USD|TRY|EUR|null), budget(string|null). "
    "Infer country_code and language from city/country when explicitly mentioned. "
    "Otherwise return null for country_code and language. "
    "Parse budget into budget_amount and budget_currency. "
    "Put explicit brand preferences in brand_include/brand_exclude; put feature requirements in must_have/nice_to_have. "
    "Handle negation: 'not Nike', 'nike olmayan' → brand_exclude. "
    "Do not invent product details. Use null for unknown fields."
)

_VAGUE_TERMS = ("best", "recommend", "good", "which", "top", "cheap", "cheapest")
_PRICE_HINTS = re.compile(
    r"(\$|€|£|usd|eur|try|tl\b|under\s+\d|below\s+\d|\d+\s*(tl|try|usd|eur))",
    re.IGNORECASE,
)


class IntentParser:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def parse(self, user_query: str) -> tuple[Intent, ParseMeta]:
        try:
            data = self._llm.complete_json(_INTENT_PROMPT, f"User shopping request: {user_query}")
            if not _is_valid_llm_payload(data):
                return _failed_parse(user_query, "invalid_or_empty_llm_payload")

            intent = _intent_from_llm_data(user_query, data)
            brand_include, brand_exclude = apply_negation_heuristics(
                user_query,
                intent.brand_include,
                intent.brand_exclude,
            )
            intent.brand_include = brand_include
            intent.brand_exclude = brand_exclude
            intent = merge_retailer_preferences(intent, user_query)

            budget_resolution = resolve_budget_currency(intent, user_query)
            return intent, _evaluate_parse(user_query, intent, data, budget_resolution)
        except Exception as err:
            return _failed_parse(user_query, str(err))


def _failed_parse(user_query: str, error: str) -> tuple[Intent, ParseMeta]:
    return empty_intent(user_query), ParseMeta(
        status="failed",
        confidence=0.0,
        needs_clarification=False,
        errors=[error],
    )


def empty_intent(user_query: str) -> Intent:
    return Intent(original_query=user_query)


def _is_valid_llm_payload(data: dict) -> bool:
    if not isinstance(data, dict) or not data:
        return False
    if set(data.keys()) == {"raw_text"}:
        return False
    return True


def _intent_from_llm_data(user_query: str, data: dict) -> Intent:
    product_type = _optional_str(data.get("product_type"))
    country_code = _clean_code(data.get("country_code"))
    language = _clean_code(data.get("language"))

    if country_code and language:
        country_code, language = normalize_market(country_code, language)
    else:
        country_code = country_code or None
        language = language or None

    amount = data.get("budget_amount")
    budget_amount = float(amount) if amount is not None else None

    return Intent(
        original_query=user_query,
        product_type=product_type,
        attributes=data.get("attributes") if isinstance(data.get("attributes"), dict) else {},
        brand_include=_norm_str_list(data.get("brand_include")),
        brand_exclude=_norm_str_list(data.get("brand_exclude")),
        must_have=_norm_str_list(data.get("must_have")),
        nice_to_have=_norm_str_list(data.get("nice_to_have")),
        budget=_optional_str(data.get("budget")),
        budget_amount=budget_amount,
        budget_currency=_norm_currency(data.get("budget_currency")),
        usage=_optional_str(data.get("usage")),
        location=_optional_str(data.get("location")),
        country_code=country_code,
        language=language,
        retailer_include=_norm_str_list(data.get("retailer_include")),
    )


def _evaluate_parse(user_query: str, intent: Intent, raw: dict, budget_resolution) -> ParseMeta:
    warnings: list[str] = []
    confidence = 0.85
    status: ParseStatus = "ok"

    if not intent.product_type:
        status = "partial"
        confidence -= 0.35
        warnings.append("product_type_missing")

    if budget_resolution.currency_inferred:
        warnings.append("budget_currency_inferred")
        confidence -= 0.1
        if status == "ok":
            status = "partial"
    elif intent.budget_amount is not None and not intent.budget_currency:
        warnings.append("budget_currency_missing")
        confidence -= 0.15
        if status == "ok":
            status = "partial"

    if intent.brand_include and intent.brand_exclude:
        overlap = {b.lower() for b in intent.brand_include} & {b.lower() for b in intent.brand_exclude}
        if overlap:
            warnings.append("brand_include_exclude_overlap")
            confidence -= 0.15

    lowered = user_query.lower()
    vague = any(term in lowered for term in _VAGUE_TERMS)
    if vague:
        confidence = min(confidence, 0.45)

    if _PRICE_HINTS.search(user_query) and intent.budget_amount is None:
        confidence -= 0.1
        warnings.append("price_mentioned_without_budget")

    needs_clarification = (
        vague
        or confidence < 0.55
        or not intent.product_type
        or budget_resolution.currency_inferred
    )
    confidence = round(max(0.0, min(1.0, confidence)), 2)

    questions = (
        _build_clarification_questions(
            intent,
            user_query,
            budget_currency_inferred=budget_resolution.currency_inferred,
        )
        if needs_clarification
        else []
    )
    if needs_clarification and budget_resolution.currency_inferred and not questions:
        questions = [currency_confirmation_question()]

    return ParseMeta(
        status=status,
        confidence=confidence,
        needs_clarification=needs_clarification,
        clarification_questions=questions[:2],
        warnings=warnings,
        budget_display=budget_resolution.budget_display,
        budget_currency_inferred=budget_resolution.currency_inferred,
    )


def _build_clarification_questions(
    intent: Intent,
    user_query: str,
    *,
    budget_currency_inferred: bool,
) -> list[str]:
    questions: list[str] = []
    if budget_currency_inferred:
        questions.append(currency_confirmation_question())
    if not intent.product_type:
        questions.append("What type of product are you looking for?")
    if intent.budget_amount is None:
        if _PRICE_HINTS.search(user_query):
            questions.append("What is your maximum budget (include currency)?")
        else:
            questions.append("What is your budget?")
    if len(questions) < 2 and not intent.brand_include and not intent.brand_exclude:
        questions.append("Any brand you prefer or want to avoid?")
    return questions[:2]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("null", "none", "n/a"):
        return None
    return text


def _clean_code(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).lower().strip()
    if not text or text in ("null", "none"):
        return None
    return text


def _norm_currency(value: object) -> str | None:
    if not value:
        return None
    code = str(value).upper().strip()
    return code if code in ("USD", "TRY", "EUR") else None


def _norm_str_list(value: object) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()]
    return []
