from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _find_dotenv() -> Path | None:
    """Locate .env in cwd or ancestors (e.g. repo root when run from a subfolder)."""
    seen: set[Path] = set()
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for directory in (start, *start.parents):
            resolved = directory.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidate = resolved / ".env"
            if candidate.is_file():
                return candidate
    return None


def _load_dotenv(dotenv_path: str | None = None) -> None:
    path = Path(dotenv_path) if dotenv_path else _find_dotenv()
    if path is None or not path.is_file():
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    serp_api_key: str = ""
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    shopping_results_per_query: int = 12
    max_recommended_links: int = 12
    min_recommended_links: int = 5
    relevance_min_score: float = 0.38
    relevance_clarify_max_score: float = 0.48
    max_immersive_lookups: int = 4
    usd_to_try_rate: float = 45.54
    use_amazon_search: bool = True
    use_trendyol_native: bool = True
    use_trendyol_serpapi_fallback: bool = True
    trendyol_fallback_min_results: int = 3
    trendyol_max_results_per_query: int = 24
    trendyol_request_timeout: int = 30

    def __post_init__(self) -> None:
        _load_dotenv()
        self.serp_api_key = os.getenv("SERP_API_KEY", self.serp_api_key)
        self.llm_provider = os.getenv("LLM_PROVIDER", self.llm_provider)
        self.openai_api_key = os.getenv("OPENAI_API_KEY", self.openai_api_key)
        self.openai_model = os.getenv("OPENAI_MODEL", self.openai_model)
        self.shopping_results_per_query = int(
            os.getenv("SHOPPING_RESULTS_PER_QUERY", str(self.shopping_results_per_query))
        )
        self.max_recommended_links = int(
            os.getenv("MAX_RECOMMENDED_LINKS", str(self.max_recommended_links))
        )
        self.min_recommended_links = int(
            os.getenv("MIN_RECOMMENDED_LINKS", str(self.min_recommended_links))
        )
        self.relevance_min_score = float(
            os.getenv("RELEVANCE_MIN_SCORE", str(self.relevance_min_score))
        )
        self.relevance_clarify_max_score = float(
            os.getenv("RELEVANCE_CLARIFY_MAX_SCORE", str(self.relevance_clarify_max_score))
        )
        self.max_immersive_lookups = int(
            os.getenv("MAX_IMMERSIVE_LOOKUPS", str(self.max_immersive_lookups))
        )
        self.usd_to_try_rate = float(os.getenv("USD_TO_TRY_RATE", str(self.usd_to_try_rate)))
        os.environ.setdefault("USD_TO_TRY_RATE", str(self.usd_to_try_rate))
        self.use_amazon_search = _env_bool("USE_AMAZON_SEARCH", self.use_amazon_search)
        self.use_trendyol_native = _env_bool("USE_TRENDYOL_NATIVE", self.use_trendyol_native)
        self.use_trendyol_serpapi_fallback = _env_bool(
            "USE_TRENDYOL_SERPAPI_FALLBACK", self.use_trendyol_serpapi_fallback
        )
        self.trendyol_fallback_min_results = int(
            os.getenv("TRENDYOL_FALLBACK_MIN_RESULTS", str(self.trendyol_fallback_min_results))
        )
        self.trendyol_max_results_per_query = int(
            os.getenv("TRENDYOL_MAX_RESULTS_PER_QUERY", str(self.trendyol_max_results_per_query))
        )
        self.trendyol_request_timeout = int(
            os.getenv("TRENDYOL_REQUEST_TIMEOUT", str(self.trendyol_request_timeout))
        )

    def validate(self) -> None:
        if not self.serp_api_key:
            raise ValueError("SERP_API_KEY is required.")
