from __future__ import annotations

from typing import Any

import requests

from .config import Settings


class SerpApiSearchError(RuntimeError):
    """Raised when SerpApi request fails."""


class SerpApiClient:
    SERP_API_URL = "https://serpapi.com/search.json"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = {**params, "api_key": self._settings.serp_api_key}
        response = requests.get(self.SERP_API_URL, params=payload, timeout=45)
        try:
            response.raise_for_status()
        except requests.HTTPError as err:
            detail = self._extract_error_detail(response)
            raise SerpApiSearchError(
                "SerpApi request failed. "
                f"HTTP {response.status_code}. {detail} "
                "Check SERP_API_KEY, account status, key restrictions, and quota."
            ) from err
        return response.json()

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
        if isinstance(error_obj, str):
            return error_obj
        return f"Response body: {str(payload)[:200]}"
