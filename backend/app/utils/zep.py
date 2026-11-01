"""Shared Zep Cloud client, request limits, and retry policy."""

from __future__ import annotations

import os
import time
from math import ceil
from collections import deque
from functools import lru_cache
from threading import Lock
from typing import Any, Callable, TypeVar

import httpx
from zep_cloud.client import Zep
from zep_cloud.core.api_error import ApiError as ZepApiError

from ..config import Config
from .logger import get_logger

logger = get_logger("mirofish.zep")

T = TypeVar("T")

ZEP_CLOUD_BASE_URL = "https://api.getzep.com/api/v2"
# Keep request behavior aligned with the zep-cloud 3.25.0 SDK default that
# MiroFish used before introducing the shared client. This is an internal
# integration policy, not a deployment setting users need to tune.
ZEP_HTTP_REQUEST_TIMEOUT_SECONDS = 60.0
# Zep ingestion is asynchronous. Medium-sized source sets can take longer than
# ten minutes even while the remote batch continues making progress, so keep a
# separate, conservative deadline from individual HTTP request timeouts.
ZEP_INGESTION_WAIT_TIMEOUT_SECONDS = 1800
MAX_ZEP_SEARCH_QUERY_CHARS = 400
MAX_ZEP_SEARCH_RESULTS = 50
# The current Zep Free plan advertises a five-request fixed window. Apply the
# same conservative rolling window locally so independent graph refreshes and
# report workers cannot race each other into a 429.
ZEP_FREE_READS_PER_MINUTE = 5
ZEP_FREE_READ_WINDOW_SECONDS = 60.0

_zep_read_rate_lock = Lock()
_zep_read_timestamps: deque[float] = deque()


def normalize_zep_search_query(query: Any) -> str:
    """Return a non-empty query within Zep Cloud's endpoint limit."""

    if not isinstance(query, str):
        raise ValueError("Zep search query must be a string")
    normalized = query.strip()
    if not normalized:
        raise ValueError("Zep search query must not be empty")
    return normalized[:MAX_ZEP_SEARCH_QUERY_CHARS]


def normalize_zep_search_limit(limit: Any) -> int:
    """Clamp a search result limit to the current Zep Cloud contract."""

    try:
        normalized = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("Zep search limit must be an integer") from exc
    if normalized < 1:
        raise ValueError("Zep search limit must be at least 1")
    return min(normalized, MAX_ZEP_SEARCH_RESULTS)


@lru_cache(maxsize=4)
def _cached_zep_client(api_key: str, timeout: float) -> Zep:
    return Zep(
        api_key=api_key,
        base_url=ZEP_CLOUD_BASE_URL,
        timeout=timeout,
    )


def get_zep_client(api_key: str | None = None, timeout: float | None = None) -> Zep:
    """Return a process-shared, explicitly configured Zep Cloud client."""

    # zep-cloud gives ZEP_API_URL precedence even when base_url is explicit.
    # Reject it so this Cloud-only integration cannot silently target a
    # self-hosted or compatibility endpoint.
    if os.environ.get("ZEP_API_URL"):
        raise ValueError("ZEP_API_URL is unsupported; unset it to use Zep Cloud")

    normalized_key = (api_key or Config.ZEP_API_KEY or "").strip()
    if not normalized_key:
        raise ValueError("ZEP_API_KEY 未配置")

    request_timeout = float(
        timeout if timeout is not None else ZEP_HTTP_REQUEST_TIMEOUT_SECONDS
    )
    if request_timeout <= 0:
        raise ValueError("Zep request timeout must be greater than 0")
    return _cached_zep_client(normalized_key, request_timeout)


def clear_zep_client_cache() -> None:
    """Clear cached clients. Intended for tests and controlled reconfiguration."""

    _cached_zep_client.cache_clear()


def clear_zep_read_rate_limit() -> None:
    """Clear local Zep read accounting for tests and controlled restarts."""

    with _zep_read_rate_lock:
        _zep_read_timestamps.clear()


def _wait_for_zep_read_slot(
    *, sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Reserve one process-wide Zep Free-plan read slot before an API call."""

    while True:
        now = time.monotonic()
        with _zep_read_rate_lock:
            while (
                _zep_read_timestamps
                and now - _zep_read_timestamps[0] >= ZEP_FREE_READ_WINDOW_SECONDS
            ):
                _zep_read_timestamps.popleft()
            if len(_zep_read_timestamps) < ZEP_FREE_READS_PER_MINUTE:
                _zep_read_timestamps.append(now)
                return
            delay = (
                ZEP_FREE_READ_WINDOW_SECONDS
                - (now - _zep_read_timestamps[0])
            )
        # Do not hold the lock while waiting: another reader may finish its
        # own request, and all waiters re-check the shared window afterwards.
        sleep(max(0.01, delay))


def is_retryable_zep_error(error: BaseException) -> bool:
    """Return whether a failed *read* is safe and useful to retry."""

    if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return True
    if isinstance(error, ZepApiError):
        status_code = error.status_code
        return status_code in {408, 429} or (
            status_code is not None and 500 <= status_code <= 599
        )
    return False


def _retry_after_seconds(error: BaseException) -> float | None:
    if not isinstance(error, ZepApiError) or not error.headers:
        return None
    value = next(
        (
            header_value
            for header_name, header_value in error.headers.items()
            if header_name.lower() == "retry-after"
        ),
        None,
    )
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _rate_limit_reset_seconds(error: BaseException) -> float | None:
    """Return seconds until Zep's rate-limit window resets, when supplied."""

    if not isinstance(error, ZepApiError) or not error.headers:
        return None
    value = next(
        (
            header_value
            for header_name, header_value in error.headers.items()
            if header_name.lower() == "x-ratelimit-reset"
        ),
        None,
    )
    if value is None:
        return None
    try:
        return max(0.0, float(value) - time.time())
    except (TypeError, ValueError):
        return None


def _retry_delay_seconds(error: BaseException, fallback_delay: float) -> float:
    """Choose a safe retry delay, including Zep's absolute reset timestamp."""

    retry_after = _retry_after_seconds(error)
    if not isinstance(error, ZepApiError) or error.status_code != 429:
        return retry_after if retry_after is not None else fallback_delay

    # Zep can return ``Retry-After: 0`` in the final second of a fixed
    # window. Retrying immediately consumes another attempt before the window
    # has reset. The absolute reset header is authoritative in that case.
    reset_after = _rate_limit_reset_seconds(error)
    delays = []
    if retry_after is not None:
        delays.append(max(1.0, retry_after))
    if reset_after is not None:
        delays.append(max(1.0, float(ceil(reset_after))))
    return max(delays, default=max(1.0, fallback_delay))


def call_zep_read_with_retry(
    operation: Callable[[], T],
    *,
    operation_name: str,
    max_attempts: int = 3,
    initial_delay: float = 2.0,
    max_delay: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Retry a safe Zep read only for transport, 408, 429, or 5xx errors."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    for attempt in range(1, max_attempts + 1):
        try:
            _wait_for_zep_read_slot(sleep=sleep)
            return operation()
        except Exception as error:
            if attempt == max_attempts or not is_retryable_zep_error(error):
                raise

            delay = min(
                _retry_delay_seconds(error, initial_delay * (2 ** (attempt - 1))),
                max_delay,
            )
            logger.warning(
                "Zep %s attempt %s/%s failed (%s); retrying in %.1fs",
                operation_name,
                attempt,
                max_attempts,
                type(error).__name__,
                delay,
            )
            sleep(delay)

    raise AssertionError("unreachable")
