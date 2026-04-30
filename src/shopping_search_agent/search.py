from __future__ import annotations

from urllib.parse import urlparse

import requests

from .config import Settings
from .models import SearchResult


class SerpApiSearchError(RuntimeError):
    """Raised when SerpApi request fails."""


class SerpApiSearchRetriever:
    SERP_API_URL = "https://serpapi.com/search.json"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search_many(self, queries: list[str]) -> list[SearchResult]:
        results: list[SearchResult] = []
        for query in queries:
            results.extend(self.search(query))
        return results

    def search(self, query: str) -> list[SearchResult]:
        params = {
            "api_key": self._settings.serp_api_key,
            "engine": "google",
            "q": query,
            "num": self._settings.search_results_per_query,
        }
        response = requests.get(self.SERP_API_URL, params=params, timeout=20)
        try:
            response.raise_for_status()
        except requests.HTTPError as err:
            detail = self._extract_error_detail(response)
            raise SerpApiSearchError(
                "SerpApi request failed. "
                f"HTTP {response.status_code}. {detail} "
                "Check SERP_API_KEY, account status, key restrictions, and quota."
            ) from err

        payload = response.json()
        items = payload.get("organic_results") or []
        parsed: list[SearchResult] = []
        for item in items:
            link = item.get("link", "")
            domain = urlparse(link).netloc.lower()
            parsed.append(
                SearchResult(
                    title=str(item.get("title", "")).strip(),
                    snippet=str(item.get("snippet", "")).strip(),
                    url=link.strip(),
                    domain=domain,
                    source_query=query,
                )
            )
        return parsed

    @staticmethod
    def _extract_error_detail(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"Response body: {response.text[:200]}"

        error_obj = payload.get("error")
        if isinstance(error_obj, dict):
            message = str(error_obj.get("message", "")).strip()
            status = str(error_obj.get("status", "")).strip()
            if message and status:
                return f"{status}: {message}"
            if message:
                return message
        return f"Response body: {str(payload)[:200]}"
