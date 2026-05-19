from __future__ import annotations

import re

# Common retail brands for negation heuristics (lowercase).
_KNOWN_BRANDS = frozenset(
    {
        "nike",
        "adidas",
        "puma",
        "reebok",
        "new balance",
        "asics",
        "samsung",
        "apple",
        "sony",
        "bose",
        "jbl",
        "xiaomi",
        "huawei",
        "lg",
        "dell",
        "hp",
        "lenovo",
        "zara",
        "h&m",
        "hm",
        "mavi",
        "koton",
        "lacoste",
        "under armour",
    }
)

_TR_BRAND_OLMAYAN = re.compile(
    r"\b(" + "|".join(re.escape(b) for b in sorted(_KNOWN_BRANDS, key=len, reverse=True)) + r")\s+olmayan\b",
    re.IGNORECASE,
)
_TR_OLMAYAN_BRAND = re.compile(
    r"\bolmayan\s+(" + "|".join(re.escape(b) for b in sorted(_KNOWN_BRANDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_EN_NEGATION = re.compile(
    r"\b(?:not|without|no)\s+(" + "|".join(re.escape(b) for b in sorted(_KNOWN_BRANDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def apply_negation_heuristics(
    query: str,
    brand_include: list[str],
    brand_exclude: list[str],
) -> tuple[list[str], list[str]]:
    """Rule-based brand_exclude; runs after LLM parse."""
    excluded = {b.lower() for b in brand_exclude}
    included = list(brand_include)

    for pattern in (_TR_BRAND_OLMAYAN, _TR_OLMAYAN_BRAND, _EN_NEGATION):
        for match in pattern.finditer(query):
            brand = _normalize_brand_token(match.group(1))
            if brand:
                excluded.add(brand.lower())
                included = [b for b in included if b.lower() != brand.lower()]

    merged_exclude = _dedupe_preserve_case(list(brand_exclude), excluded)
    return included, merged_exclude


def _normalize_brand_token(raw: str) -> str | None:
    token = raw.strip()
    if not token:
        return None
    lowered = token.lower()
    if lowered in _KNOWN_BRANDS:
        return token.title() if lowered != "h&m" else "H&M"
    return token.title()


def _dedupe_preserve_case(existing: list[str], lowered_set: set[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for brand in existing:
        key = brand.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(brand)
    for key in lowered_set:
        if key in seen:
            continue
        seen.add(key)
        out.append(key.title() if key != "h&m" else "H&M")
    return out
