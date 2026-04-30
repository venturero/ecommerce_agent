from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Intent, RankedLink, SearchResult


class RankingFilter:
    TRUSTED_DOMAIN_WEIGHTS = {
        "trendyol.com": 1.6,
        "amazon.com": 1.6,
        "hepsiburada.com": 1.5,
        "n11.com": 1.4,
        "mediamarkt.com.tr": 1.4,
        "nike.com": 1.5,
        "adidas.com": 1.5,
    }
    SPAM_TERMS = {"seo", "backlink", "coupon code generator", "free traffic", "sponsored post"}

    def rank(self, intent: Intent, results: list[SearchResult], top_k: int) -> list[RankedLink]:
        deduped = self._dedupe(results)
        scored: list[RankedLink] = []
        for item in deduped:
            score = self._score(intent, item)
            if score <= 0:
                continue
            scored.append(
                RankedLink(
                    title=item.title,
                    url=item.url,
                    domain=item.domain,
                    snippet=item.snippet,
                    score=round(score, 4),
                )
            )
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

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
            [(k, v) for (k, v) in parse_qsl(split.query, keep_blank_values=True) if not k.startswith("utm_")]
        )
        return urlunsplit((split.scheme, split.netloc, split.path, cleaned_query, split.fragment))

    def _score(self, intent: Intent, item: SearchResult) -> float:
        haystack = f"{item.title} {item.snippet}".lower()
        score = 1.0

        product_tokens = re.findall(r"[a-z0-9]+", intent.product_type.lower())
        token_hits = sum(1 for t in product_tokens if t in haystack)
        score += min(2.5, 0.5 * token_hits)

        for attr in intent.attributes:
            if attr.lower() in haystack:
                score += 0.35

        domain_weight = self._domain_weight(item.domain)
        score *= domain_weight

        lowered = haystack.lower()
        if any(term in lowered for term in self.SPAM_TERMS):
            score *= 0.3

        if "blog" in item.domain and "buy" not in lowered and "shop" not in lowered:
            score *= 0.75

        return score

    def _domain_weight(self, domain: str) -> float:
        for trusted, weight in self.TRUSTED_DOMAIN_WEIGHTS.items():
            if domain.endswith(trusted):
                return weight
        return 1.0
