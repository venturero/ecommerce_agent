"""Retry helpers for transient external API failures."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import requests

T = TypeVar("T")

MAX_ATTEMPTS = 2


def is_transient_request_error(err: BaseException) -> bool:
    if isinstance(err, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(err, requests.HTTPError):
        response = err.response
        if response is not None and response.status_code >= 500:
            return True
    return False


def is_transient_llm_error(err: BaseException) -> bool:
    if isinstance(err, (TimeoutError,)):
        return True
    try:
        from openai import APIConnectionError, APITimeoutError, APIStatusError

        if isinstance(err, (APITimeoutError, APIConnectionError)):
            return True
        if isinstance(err, APIStatusError) and err.status_code >= 500:
            return True
    except ImportError:
        pass
    try:
        import httpx

        if isinstance(err, httpx.TimeoutException):
            return True
    except ImportError:
        pass
    cause = err.__cause__
    if cause is not None and cause is not err:
        return is_transient_llm_error(cause)
    return False


def call_with_retry(
    fn: Callable[[], T],
    *,
    is_retryable: Callable[[BaseException], bool],
    max_attempts: int = MAX_ATTEMPTS,
) -> T:
    last: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except BaseException as err:
            last = err
            if attempt + 1 >= max_attempts or not is_retryable(err):
                raise
    assert last is not None  # pragma: no cover
    raise last
