from __future__ import annotations

from typing import Any

import requests

from .config import Settings
from .retry import call_with_retry, is_transient_request_error


class SerpApiSearchError(RuntimeError):
    """Raised when SerpApi request fails."""


class SerpApiClient:
    SERP_API_URL = "https://serpapi.com/search.json"
    REQUEST_TIMEOUT = 45

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = {**params, "api_key": self._settings.serp_api_key}

        def _fetch() -> requests.Response:
            response = requests.get(
                self.SERP_API_URL, params=payload, timeout=self.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response

        try:
            response = call_with_retry(_fetch, is_retryable=is_transient_request_error)
        except requests.Timeout as err:
            raise SerpApiSearchError(
                "SerpApi request timed out. Check network connectivity and try again."
            ) from err
        except requests.ConnectionError as err:
            raise SerpApiSearchError(
                "SerpApi connection failed. Check network connectivity and try again."
            ) from err
        except requests.HTTPError as err:
            http_response = err.response
            status = http_response.status_code if http_response is not None else "unknown"
            detail = (
                self._extract_error_detail(http_response)
                if http_response is not None
                else str(err)
            )
            raise SerpApiSearchError(
                "SerpApi request failed. "
                f"HTTP {status}. {detail} "
                "Check SERP_API_KEY, account status, key restrictions, and quota."
            ) from err

        payload = response.json()
        api_error = payload.get("error")
        if api_error:
            detail = api_error if isinstance(api_error, str) else str(api_error)
            raise SerpApiSearchError(f"SerpApi error: {detail}")
        return payload

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
