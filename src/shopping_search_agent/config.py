from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv(dotenv_path: str = ".env") -> None:
    if not os.path.exists(dotenv_path):
        return

    with open(dotenv_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


@dataclass
class Settings:
    serp_api_key: str = ""
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    search_results_per_query: int = 5
    max_recommended_links: int = 8
    min_recommended_links: int = 5

    def __post_init__(self) -> None:
        _load_dotenv()
        self.serp_api_key = os.getenv("SERP_API_KEY", self.serp_api_key)
        self.llm_provider = os.getenv("LLM_PROVIDER", self.llm_provider)
        self.openai_api_key = os.getenv("OPENAI_API_KEY", self.openai_api_key)
        self.openai_model = os.getenv("OPENAI_MODEL", self.openai_model)
        self.search_results_per_query = int(
            os.getenv("SEARCH_RESULTS_PER_QUERY", str(self.search_results_per_query))
        )
        self.max_recommended_links = int(
            os.getenv("MAX_RECOMMENDED_LINKS", str(self.max_recommended_links))
        )
        self.min_recommended_links = int(
            os.getenv("MIN_RECOMMENDED_LINKS", str(self.min_recommended_links))
        )

    def validate(self) -> None:
        if not self.serp_api_key:
            raise ValueError("SERP_API_KEY is required.")
