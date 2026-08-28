"""Reusable rate-limit + retry + circuit-breaker for connector HTTP calls.

Extracted from the inline retry loops in src/connectors/notion.py and
src/connectors/gdocs.py (both implemented 3 req/sec + exponential backoff +
Retry-After honoring). This module unifies the pattern so:

  * linear.py (no rate limiting today) gets the same protections
  * notion.py and gdocs.py stop duplicating the loop
  * Future connectors get drop-in safety with one line

Usage:
    limiter = RateLimiter(requests_per_second=3.0, max_retries=5)
    data = await limiter.request_json(
        client, "GET", "/v1/pages/123",
        retry_on_status={429},
        is_retryable_403=lambda r: _is_quota_error(r),  # gdocs idiom
    )
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CircuitOpenError(RuntimeError):
    """Raised when the breaker has tripped after consecutive failures."""


class RateLimiter:
    """Token-bucket throttle + exponential backoff + circuit breaker.

    Conservative defaults match the notion/gdocs prior art (3 req/sec,
    5 retries). Circuit breaker is OFF by default (max_consecutive_failures=0)
    because the prior connectors didn't use one; opt in by passing a value.
    """

    def __init__(
        self,
        *,
        requests_per_second: float = 3.0,
        max_retries: int = 5,
        backoff_base: float = 0.5,
        backoff_jitter: float = 0.25,
        max_consecutive_failures: int = 0,
        name: str = "connector",
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be > 0")
        self._min_interval = 1.0 / requests_per_second
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_jitter = backoff_jitter
        self._max_consecutive_failures = max_consecutive_failures
        self._name = name

        self._lock = asyncio.Lock()
        self._next_allowed_at: float = 0.0
        self._consecutive_failures: int = 0
        self._circuit_opened_until: float | None = None

    # ── public API ────────────────────────────────────────────────────

    async def acquire(self) -> None:
        """Block until the next request slot is allowed.

        Raises CircuitOpenError if the breaker is currently open.
        """
        if self._circuit_opened_until is not None:
            now = time.monotonic()
            if now < self._circuit_opened_until:
                raise CircuitOpenError(
                    f"{self._name} circuit open until "
                    f"{self._circuit_opened_until - now:.1f}s from now"
                )
            self._circuit_opened_until = None
            self._consecutive_failures = 0

        async with self._lock:
            now = time.monotonic()
            wait = self._next_allowed_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_allowed_at = now + self._min_interval

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        if self._max_consecutive_failures <= 0:
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._max_consecutive_failures:
            # Open the circuit for max_retries * backoff window (rough cap)
            window = max(2.0, self._backoff_base * (2 ** self._max_retries))
            self._circuit_opened_until = time.monotonic() + window
            logger.warning(
                "%s circuit OPEN after %d failures; cooling for %.1fs",
                self._name,
                self._consecutive_failures,
                window,
            )

    async def request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        retry_on_status: set[int] | None = None,
        raise_on_status: dict[int, type[Exception]] | None = None,
        is_retryable_403: Callable[[httpx.Response], bool] | None = None,
    ) -> dict:
        """Execute a JSON-returning HTTP request with full retry/backoff.

        Args:
            retry_on_status: HTTP statuses that trigger backoff+retry.
                Defaults to {429}.
            raise_on_status: status -> exception class mapping for
                immediate raises (e.g. {401: NotionAuthError}).
            is_retryable_403: optional predicate to treat some 403 responses
                as retryable (gdocs quota errors).
        """
        retry_on_status = retry_on_status or {429}
        raise_on_status = raise_on_status or {}

        for attempt in range(self._max_retries + 1):
            await self.acquire()

            try:
                response = await client.request(method, url, params=params, json=json)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                self.record_failure()
                if attempt >= self._max_retries:
                    raise
                await self._sleep_backoff(attempt, retry_after=None, reason=str(e))
                continue

            for status, exc_cls in raise_on_status.items():
                if response.status_code == status:
                    raise exc_cls(
                        f"{self._name} returned {status} - {response.text[:200]}"
                    )

            should_retry = response.status_code in retry_on_status or (
                response.status_code == 403
                and is_retryable_403 is not None
                and is_retryable_403(response)
            )
            if should_retry:
                self.record_failure()
                if attempt >= self._max_retries:
                    response.raise_for_status()
                await self._sleep_backoff(
                    attempt,
                    retry_after=_parse_retry_after(response),
                    reason=str(response.status_code),
                    url=url,
                )
                continue

            response.raise_for_status()
            self.record_success()
            return response.json()

        raise RuntimeError(f"{self._name} request exhausted retries")

    # ── internals ─────────────────────────────────────────────────────

    async def _sleep_backoff(
        self,
        attempt: int,
        *,
        retry_after: float | None,
        reason: str,
        url: str | None = None,
    ) -> None:
        exp = (2 ** attempt) * self._backoff_base + random.uniform(0, self._backoff_jitter)
        delay = max(retry_after or 0.0, exp)
        logger.info(
            "%s backoff attempt=%d sleep=%.2fs reason=%s url=%s",
            self._name,
            attempt,
            delay,
            reason,
            url or "?",
        )
        await asyncio.sleep(delay)


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
