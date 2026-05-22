from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .market import (
    exceeds_budget,
    is_allowed_retailer_domain,
    is_product_page,
    is_search_or_category_page,
    locale_url_multiplier,
    market_for_search,
    price_exceeds_budget,
)
from .models import Intent, ParseMeta, RankedLink, SearchResult
from .parse_policy import (
    apply_brand_exclude_filter,
    apply_brand_include_filter,
    apply_budget_filter,
    apply_must_have_filter,
    apply_strict_score_boosts,
)
from .event_tracking import get_session_preferences
from .preference_transparency import (
    build_base_ranking_signals,
    build_why_seeing_this,
    capped_preference_boost,
)
from .retailer_preference import result_matches_retailer_preferences


_MUST_HAVE_VARIANTS: dict[str, tuple[str, ...]] = {
    "armless": ("armless", "kolsuz", "sleeveless", "sızır kol", "sifir kol", "sıfır kol", "tank"),
    "white": ("white", "beyaz"),
    "black": ("black", "siyah"),
    "man": ("man", "men", "erkek", "male"),
    "men": ("man", "men", "erkek", "male"),
    "woman": ("woman", "women", "kadın", "kadin", "female"),
    "women": ("woman", "women", "kadın", "kadin", "female"),
}


class RankingFilter:
    TRUSTED_DOMAIN_WEIGHTS = {
        "amazon.com.tr": 1.7,
        "trendyol.com": 1.65,
        "amazon.com": 1.2,
    }
    SPAM_TERMS = {"seo", "backlink", "coupon code generator", "free traffic", "sponsored post"}
    ENGINE_WEIGHTS = {
        "trendyol": 1.3,
        "amazon": 1.25,
        "google_shopping": 1.05,
        "google_immersive": 1.0,
        "google": 0.9,
    }

    def rank(
        self,
        intent: Intent,
        results: list[SearchResult],
        top_k: int,
        parse_meta: ParseMeta,
        session_id: str | None = None,
        personalization_enabled: bool = True,
    ) -> list[RankedLink]:
        market = market_for_search(intent)
        status = parse_meta.status
        use_personalization = personalization_enabled and bool(session_id)
        preference_counts = (
            get_session_preferences(session_id) if use_personalization else {}
        )
        deduped = self._dedupe(results)
        use_tr_variants = market.country_code == "tr" or bool(intent.retailer_include)
        scored: list[RankedLink] = []
        for item in deduped:
            if not result_matches_retailer_preferences(item.domain, intent.retailer_include):
                continue
            if not is_allowed_retailer_domain(item.domain, market.country_code):
                continue
            if item.in_stock is False:
                continue

            haystack = self._result_haystack(item)

            if apply_brand_exclude_filter(status) and self._matches_any(haystack, intent.brand_exclude):
                continue
            if apply_brand_include_filter(status) and intent.brand_include:
                if not self._matches_any(haystack, intent.brand_include):
                    continue
            if apply_must_have_filter(status) and intent.must_have:
                if not self._matches_all_must_have(haystack, intent.must_have, use_tr_variants):
                    continue

            if apply_budget_filter(status):
                if price_exceeds_budget(
                    item.extracted_price,
                    item.price_currency,
                    intent.budget_amount,
                    intent.budget_currency,
                ):
                    continue
                if item.extracted_price is None and exceeds_budget(
                    haystack, intent.budget_amount, intent.budget_currency
                ):
                    continue

            base_score = self._score(intent, item, market, parse_meta)
            pref_boost, pref_signals = (
                capped_preference_boost(item.domain, preference_counts)
                if use_personalization
                else (0.0, [])
            )
            score = base_score + pref_boost
            if score <= 0:
                continue

            domain_weight = self._domain_weight(item.domain)
            engine_weight = self.ENGINE_WEIGHTS.get(item.source_engine, 1.0)
            retailer_matched = result_matches_retailer_preferences(
                item.domain, intent.retailer_include
            )
            base_signals = build_base_ranking_signals(
                intent,
                item,
                domain_weight=domain_weight,
                engine_weight=engine_weight,
                retailer_matched=retailer_matched,
            )
            why_seeing_this = build_why_seeing_this(
                base_signals,
                pref_signals,
                personalization_enabled=use_personalization,
            )

            scored.append(
                RankedLink(
                    title=item.title,
                    url=item.url,
                    domain=item.domain,
                    snippet=item.snippet,
                    score=round(score, 4),
                    why_seeing_this=why_seeing_this,
                    source_engine=item.source_engine,
                    extracted_price=item.extracted_price,
                    price_currency=item.price_currency,
                    price_display=item.price_display,
                    in_stock=item.in_stock,
                    merchant=item.merchant,
                )
            )
        scored.sort(key=lambda x: x.score, reverse=True)
        return self._select_diverse(scored, top_k)

    def _select_diverse(self, ranked: list[RankedLink], top_k: int) -> list[RankedLink]:
        if not ranked:
            return []

        selected: list[RankedLink] = []
        per_domain: dict[str, int] = {}
        used_urls: set[str] = set()

        def retailer_bucket(link: RankedLink) -> str:
            host = link.domain.lower()
            if "trendyol.com" in host:
                return "trendyol"
            return "amazon"

        for link in ranked:
            if len(selected) >= top_k:
                break
            key = retailer_bucket(link)
            if per_domain.get(key, 0) >= 1:
                continue
            if link.url in used_urls:
                continue
            selected.append(link)
            per_domain[key] = per_domain.get(key, 0) + 1
            used_urls.add(link.url)

        max_per_retailer = max(3, top_k // 2)
        for link in ranked:
            if len(selected) >= top_k:
                break
            if link.url in used_urls:
                continue
            key = retailer_bucket(link)
            if per_domain.get(key, 0) >= max_per_retailer:
                continue
            selected.append(link)
            per_domain[key] = per_domain.get(key, 0) + 1
            used_urls.add(link.url)

        return selected[:top_k]

    def _dedupe(self, results: list[SearchResult]) -> list[SearchResult]:
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for result in results:
            canonical = self._canonicalize_url(result.url)
            if canonical in seen:
                continue
            seen.add(canonical)
            result.url = canonical
            deduped.append(result)
        return deduped

    @staticmethod
    def _canonicalize_url(url: str) -> str:
        split = urlsplit(url)
        cleaned_query = urlencode(
            [
                (k, v)
                for (k, v) in parse_qsl(split.query, keep_blank_values=True)
                if not k.startswith("utm_") and k.lower() not in ("gads", "ref", "srsltid")
            ]
        )
        return urlunsplit((split.scheme, split.netloc, split.path, cleaned_query, split.fragment))

    def _score(self, intent: Intent, item: SearchResult, market, parse_meta: ParseMeta) -> float:
        haystack = f"{item.title} {item.snippet}".lower()
        score = 1.0

        if intent.product_type:
            product_tokens = re.findall(r"[a-z0-9]+", intent.product_type.lower())
            token_hits = sum(1 for t in product_tokens if t in haystack)
            score += min(2.5, 0.5 * token_hits)

        for attr in intent.attributes:
            if attr.lower() in haystack:
                score += 0.35

        if apply_strict_score_boosts(parse_meta.status):
            for term in intent.must_have:
                if term.lower() in haystack:
                    score += 0.4
            for term in intent.nice_to_have:
                if term.lower() in haystack:
                    score += 0.25
            for brand in intent.brand_include:
                if brand.lower() in haystack:
                    score += 0.5

        score *= self._domain_weight(item.domain)
        score *= locale_url_multiplier(item.url, market)
        score *= self._url_kind_multiplier(item.url)
        score *= self.ENGINE_WEIGHTS.get(item.source_engine, 1.0)

        if item.extracted_price is not None:
            score += 0.5
        if item.in_stock is True:
            score += 0.35

        lowered = haystack.lower()
        if any(term in lowered for term in self.SPAM_TERMS):
            score *= 0.3

        if "blog" in item.domain and "buy" not in lowered and "shop" not in lowered:
            score *= 0.75

        return score

    @staticmethod
    def _url_kind_multiplier(url: str) -> float:
        if is_product_page(url):
            return 1.6
        if is_search_or_category_page(url):
            return 0.25
        return 0.9

    def _domain_weight(self, domain: str) -> float:
        for trusted, weight in self.TRUSTED_DOMAIN_WEIGHTS.items():
            if domain.endswith(trusted):
                return weight
        return 1.0

    @staticmethod
    def _result_haystack(item: SearchResult) -> str:
        return f"{item.title} {item.snippet} {item.merchant or ''} {item.price_display or ''}".lower()

    @staticmethod
    def _matches_any(haystack: str, terms: list[str]) -> bool:
        return any(term.lower() in haystack for term in terms if term.strip())

    @staticmethod
    def _matches_all(haystack: str, terms: list[str]) -> bool:
        cleaned = [term for term in terms if term.strip()]
        if not cleaned:
            return True
        return all(term.lower() in haystack for term in cleaned)

    @classmethod
    def _matches_all_must_have(
        cls, haystack: str, terms: list[str], use_tr_variants: bool
    ) -> bool:
        cleaned = [term for term in terms if term.strip()]
        if not cleaned:
            return True
        if not use_tr_variants:
            return cls._matches_all(haystack, cleaned)
        for term in cleaned:
            variants = _MUST_HAVE_VARIANTS.get(term.lower(), (term,))
            if not any(variant.lower() in haystack for variant in variants):
                return False
        return True
