from __future__ import annotations

from shopping_search_agent.decision_summary import (
    build_decision_summary,
    build_follow_up_chips,
    build_shareable_markdown,
)


def _item(
    title: str,
    *,
    domain: str = "amazon.com",
    price: str | None = None,
    extracted_price: float | None = None,
    explanation: str = "",
    snippet: str = "",
) -> dict:
    return {
        "title": title,
        "url": f"https://{domain}/p",
        "domain": domain,
        "price": price,
        "extracted_price": extracted_price,
        "price_currency": "USD" if extracted_price is not None else None,
        "explanation": explanation,
        "snippet": snippet,
    }


def test_build_decision_summary_uses_must_have_signals():
    response = {
        "route": "shopping",
        "query": "waterproof running shoes",
        "constraints": {"product_type": "running shoes", "must_have": ["waterproof"]},
        "shortlist": [
            _item("Aqua Run", snippet="waterproof trail runner", domain="amazon.com"),
            _item("Basic Jog", snippet="mesh upper casual", domain="trendyol.com"),
        ],
    }
    lines = build_decision_summary(response)
    assert lines
    assert len(lines) <= 6
    assert any("waterproof" in line.lower() for line in lines)
    assert any("trade-off" in line.lower() for line in lines)
    assert not any("best product" in line.lower() for line in lines)


def test_build_decision_summary_price_tradeoff():
    response = {
        "route": "shopping",
        "query": "headphones",
        "constraints": {"product_type": "headphones", "must_have": []},
        "shortlist": [
            _item("Budget Buds", extracted_price=49.0, domain="amazon.com"),
            _item("Pro Buds", extracted_price=129.0, domain="bestbuy.com"),
        ],
    }
    lines = build_decision_summary(response)
    assert any("lower listed price" in line.lower() for line in lines)
    assert any("trade-off" in line.lower() for line in lines)


def test_build_decision_summary_empty_when_single_item():
    response = {
        "route": "shopping",
        "query": "shoes",
        "constraints": {},
        "shortlist": [_item("Only One")],
    }
    assert build_decision_summary(response) == []


def test_build_decision_summary_no_fabricated_durability_without_query_term():
    response = {
        "route": "shopping",
        "query": "running shoes",
        "constraints": {"must_have": []},
        "shortlist": [
            _item("Rugged Max", snippet="extra durable sole", domain="a.com"),
            _item("Lite Run", snippet="lightweight mesh", domain="b.com"),
        ],
    }
    lines = build_decision_summary(response)
    assert not any("durable" in line.lower() for line in lines)


def test_build_shareable_markdown_includes_query_options_and_tradeoffs():
    response = {
        "route": "shopping",
        "query": "waterproof running shoes under $120",
        "constraints": {
            "product_type": "running shoes",
            "must_have": ["waterproof"],
            "budget": "under $120",
        },
        "shortlist": [
            _item(
                "Aqua Run",
                domain="amazon.com",
                price="$99",
                extracted_price=99.0,
                snippet="waterproof trail",
                explanation="Matches waterproof intent.",
            ),
            _item("Lite Walk", domain="trendyol.com", snippet="mesh upper"),
        ],
        "disclaimer": "Verify on retailer.",
    }
    md = build_shareable_markdown(response)
    assert "## Your request" in md
    assert "waterproof running shoes" in md
    assert "## Intent" in md
    assert "running shoes" in md
    assert "## Options" in md
    assert "amazon.com" in md
    assert "## Trade-offs" in md
    assert "Verify on retailer" in md


def test_build_follow_up_chips_are_context_aware():
    response = {
        "route": "shopping",
        "query": "waterproof running shoes",
        "constraints": {"product_type": "running shoes", "must_have": ["waterproof"]},
        "shortlist": [
            _item("A", domain="amazon.com", extracted_price=100.0),
            _item("B", domain="trendyol.com", extracted_price=80.0),
        ],
    }
    chips = build_follow_up_chips(response)
    assert len(chips) <= 4
    labels = [c["label"] for c in chips]
    assert "Compare top 2" in labels
    assert "Cheaper" in labels
    queries = " ".join(c["query"] for c in chips).lower()
    assert "running shoes" in queries or "waterproof" in queries
