from __future__ import annotations

from .market import budget_limit_try, market_for_search
from .models import Intent, ParseMeta


class QueryGenerator:
    def primary_query(self, intent: Intent, parse_meta: ParseMeta) -> str:
        if parse_meta.status == "failed":
            return intent.original_query.strip()

        product = (intent.product_type or "").strip()
        attr_phrase = self._attr_phrase(intent)

        if parse_meta.status == "partial":
            parts = [product, attr_phrase]
            return " ".join(p for p in parts if p).strip() or intent.original_query.strip()

        brand_phrase = " ".join(intent.brand_include[:2])
        must_phrase = " ".join(intent.must_have[:4])
        query = f"{brand_phrase} {product} {must_phrase} {attr_phrase}".strip()
        return query or intent.original_query.strip()

    def trendyol_queries(self, intent: Intent, parse_meta: ParseMeta) -> list[str]:
        if parse_meta.status == "failed":
            return [intent.original_query.strip()]

        base = self.primary_query(intent, parse_meta)
        market = market_for_search(intent)
        queries = [base]

        if market.country_code == "tr" and intent.product_type:
            queries.append(self._turkish_query(intent))
            max_try = budget_limit_try(intent.budget_amount, intent.budget_currency)
            if max_try and parse_meta.status in ("ok", "partial"):
                queries.append(f"{base} {max_try} TL altı")
        elif intent.budget_amount is not None and parse_meta.status in ("ok", "partial"):
            queries.append(f"{base} under ${int(intent.budget_amount)}")

        if parse_meta.status == "ok" and intent.nice_to_have:
            nice_phrase = " ".join(intent.nice_to_have[:3])
            queries.append(f"{base} {nice_phrase}".strip())

        return self._dedupe(queries)[:4]

    def legacy_queries(self, intent: Intent, parse_meta: ParseMeta) -> list[str]:
        primary = self.primary_query(intent, parse_meta)
        trendyol = self.trendyol_queries(intent, parse_meta)
        return self._dedupe([primary, *trendyol])

    @staticmethod
    def _turkish_query(intent: Intent) -> str:
        if not intent.product_type:
            return intent.original_query
        mapping = {
            "running shoes": "su geçirmez koşu ayakkabısı",
            "sneaker": "su geçirmez spor ayakkabı",
            "shoes": "su geçirmez ayakkabı",
        }
        lowered = intent.product_type.lower()
        for key, tr in mapping.items():
            if key in lowered:
                if "waterproof" in {k.lower() for k in intent.attributes} or any(
                    str(v).lower() in ("true", "1", "yes") for k, v in intent.attributes.items() if k == "waterproof"
                ):
                    return tr
                return tr.replace("su geçirmez ", "")
        return intent.product_type

    @staticmethod
    def _attr_phrase(intent: Intent) -> str:
        parts: list[str] = []
        for key, value in intent.attributes.items():
            normalized = str(value).lower()
            if normalized in ("true", "1", "yes"):
                parts.append(key)
            elif normalized not in ("false", "0", "no"):
                parts.append(f"{key} {value}")
        return " ".join(parts).strip()

    @staticmethod
    def _dedupe(queries: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for q in queries:
            normalized = " ".join(q.split())
            if normalized and normalized.lower() not in seen:
                seen.add(normalized.lower())
                deduped.append(normalized)
        return deduped

    def generate(self, intent: Intent, parse_meta: ParseMeta) -> list[str]:
        return self.legacy_queries(intent, parse_meta)
