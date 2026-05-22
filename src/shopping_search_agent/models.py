from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Route = Literal["shopping", "chitchat"]
SearchEngine = Literal["google", "google_shopping", "amazon", "google_immersive", "trendyol"]


ParseStatus = Literal["ok", "partial", "failed", "skipped"]


@dataclass
class ParseMeta:
    status: ParseStatus
    confidence: float | None = None
    needs_clarification: bool = False
    clarification_questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    budget_display: str | None = None
    budget_currency_inferred: bool = False


@dataclass
class Intent:
    original_query: str
    product_type: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    brand_include: list[str] = field(default_factory=list)
    brand_exclude: list[str] = field(default_factory=list)
    must_have: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    budget: str | None = None
    budget_amount: float | None = None
    budget_currency: str | None = None
    usage: str | None = None
    location: str | None = None
    country_code: str | None = None
    language: str | None = None
    retailer_include: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    domain: str
    source_query: str
    source_engine: SearchEngine = "google"
    extracted_price: float | None = None
    price_currency: str | None = None
    price_display: str | None = None
    in_stock: bool | None = None
    merchant: str | None = None


@dataclass
class RankedLink:
    title: str
    url: str
    domain: str
    snippet: str
    score: float
    explanation: str = ""
    why_seeing_this: str = ""
    source_engine: SearchEngine = "google"
    extracted_price: float | None = None
    price_currency: str | None = None
    price_display: str | None = None
    in_stock: bool | None = None
    merchant: str | None = None
