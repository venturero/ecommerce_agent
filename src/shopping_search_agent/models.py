from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Route = Literal["shopping", "chitchat"]


@dataclass
class Intent:
    original_query: str
    product_type: str
    attributes: dict[str, str] = field(default_factory=dict)
    budget: str | None = None
    usage: str | None = None


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    domain: str
    source_query: str


@dataclass
class RankedLink:
    title: str
    url: str
    domain: str
    snippet: str
    score: float
    explanation: str = ""
