from __future__ import annotations

from .models import Intent


class QueryGenerator:
    HIGH_TRUST_DOMAINS = [
        "trendyol.com",
        "amazon.com",
        "hepsiburada.com",
        "n11.com",
        "mediamarkt.com.tr",
        "nike.com",
        "adidas.com",
    ]

    def generate(self, intent: Intent) -> list[str]:
        attr_phrase = " ".join(
            [f"{k}:{v}" if v not in ("true", "false") else k for k, v in intent.attributes.items()]
        ).strip()
        base = f"{intent.product_type} {attr_phrase}".strip()

        queries = [
            f"best {base}".strip(),
            f"buy {base} online".strip(),
            f"{base} official store".strip(),
            f"{base} reviews and price".strip(),
        ]

        if intent.budget:
            queries.append(f"{base} under {intent.budget}".strip())

        for domain in self.HIGH_TRUST_DOMAINS[:3]:
            queries.append(f"{base} site:{domain}".strip())

        seen: set[str] = set()
        deduped: list[str] = []
        for q in queries:
            normalized = " ".join(q.split())
            if normalized and normalized.lower() not in seen:
                seen.add(normalized.lower())
                deduped.append(normalized)
        return deduped
