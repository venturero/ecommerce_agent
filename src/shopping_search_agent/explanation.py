from __future__ import annotations

from .llm import LLMClient
from .models import Intent, RankedLink


class ExplanationLayer:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def enrich(self, intent: Intent, links: list[RankedLink]) -> list[RankedLink]:
        enriched: list[RankedLink] = []
        for link in links:
            explanation = self._generate_explanation(intent, link)
            link.explanation = explanation
            enriched.append(link)
        return enriched

    def _generate_explanation(self, intent: Intent, link: RankedLink) -> str:
        system_prompt = (
            "You explain why a search result is relevant to a shopping intent. "
            "Use only provided title/snippet/url/domain evidence. "
            "Never claim exact stock, price, discounts, or delivery info."
        )
        user_prompt = (
            f"Intent product_type={intent.product_type or 'unspecified'}, attributes={intent.attributes}, "
            f"brand_include={intent.brand_include}, brand_exclude={intent.brand_exclude}, "
            f"must_have={intent.must_have}, nice_to_have={intent.nice_to_have}, "
            f"budget={intent.budget}, usage={intent.usage}, location={intent.location}\n"
            f"Result title={link.title}\nResult snippet={link.snippet}\n"
            f"Result domain={link.domain}\nResult url={link.url}\n"
            f"Listed price={link.price_display}\nStock hint={link.in_stock}\n"
            "Return one concise sentence."
        )
        try:
            text = self._llm.complete_text(system_prompt, user_prompt)
            return text.replace("\n", " ").strip()
        except Exception:
            return (
                f"This result appears relevant to {intent.product_type or 'your request'} based on its title/snippet and comes from "
                f"{link.domain}, which is often used for product discovery."
            )
