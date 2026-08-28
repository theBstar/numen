"""Tests for src/connectors/_rate_limit.py."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import httpx
import pytest

from src.connectors._rate_limit import (
    CircuitOpenError,
    RateLimiter,
    _parse_retry_after,
)


def _make_response(status: int, *, body: dict | None = None, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        headers=headers or {},
        json=body if body is not None else {},
        request=httpx.Request("GET", "https://test/x"),
    )


def _make_client(responses: list) -> AsyncMock:
    client = AsyncMock()
    iter_responses = iter(responses)
    async def _request(method, url, params=None, json=None):
        nxt = next(iter_responses)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt
    client.request = AsyncMock(side_effect=_request)
    return client


# ── happy path ────────────────────────────────────────────────────────


async def test_request_json_returns_payload_on_200():
    limiter = RateLimiter(requests_per_second=100, name="test")
    client = _make_client([_make_response(200, body={"ok": True})])
    out = await limiter.request_json(client, "GET", "/x")
    assert out == {"ok": True}


# ── 429 + backoff + retry ─────────────────────────────────────────────


async def test_429_then_200_succeeds():
    limiter = RateLimiter(requests_per_second=1000, max_retries=3, backoff_base=0.001, backoff_jitter=0.001, name="t")
    client = _make_client([
        _make_response(429, headers={"Retry-After": "0"}),
        _make_response(200, body={"ok": 1}),
    ])
    out = await limiter.request_json(client, "GET", "/x")
    assert out == {"ok": 1}
    assert client.request.await_count == 2


async def test_429_exhausted_raises():
    limiter = RateLimiter(requests_per_second=1000, max_retries=2, backoff_base=0.001, backoff_jitter=0.001, name="t")
    client = _make_client([_make_response(429) for _ in range(3)])
    with pytest.raises(httpx.HTTPStatusError):
        await limiter.request_json(client, "GET", "/x")


async def test_retry_after_header_is_honored():
    limiter = RateLimiter(requests_per_second=1000, max_retries=2, backoff_base=0.001, backoff_jitter=0.001, name="t")
    client = _make_client([
        _make_response(429, headers={"Retry-After": "0.05"}),
        _make_response(200, body={}),
    ])
    start = time.monotonic()
    await limiter.request_json(client, "GET", "/x")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05


async def test_invalid_retry_after_falls_back_to_exp_backoff():
    limiter = RateLimiter(requests_per_second=1000, max_retries=2, backoff_base=0.001, backoff_jitter=0.0, name="t")
    client = _make_client([
        _make_response(429, headers={"Retry-After": "not-a-number"}),
        _make_response(200, body={}),
    ])
    out = await limiter.request_json(client, "GET", "/x")
    assert out == {}


# ── 403 quota predicate (gdocs idiom) ─────────────────────────────────


async def test_403_with_quota_predicate_retries():
    limiter = RateLimiter(requests_per_second=1000, max_retries=2, backoff_base=0.001, backoff_jitter=0.0, name="t")
    client = _make_client([
        _make_response(403, body={"error": {"reason": "rateLimitExceeded"}}),
        _make_response(200, body={"ok": True}),
    ])
    out = await limiter.request_json(
        client, "GET", "/x",
        is_retryable_403=lambda r: r.json().get("error", {}).get("reason") == "rateLimitExceeded",
    )
    assert out == {"ok": True}


async def test_403_without_quota_predicate_raises():
    limiter = RateLimiter(requests_per_second=1000, max_retries=2, backoff_base=0.001, backoff_jitter=0.0, name="t")
    client = _make_client([_make_response(403, body={"error": "forbidden"})])
    with pytest.raises(httpx.HTTPStatusError):
        await limiter.request_json(client, "GET", "/x")


# ── raise_on_status maps to custom exception ──────────────────────────


class _AuthError(Exception):
    pass


async def test_raise_on_status_dispatches_custom_exception():
    limiter = RateLimiter(requests_per_second=1000, name="t")
    client = _make_client([_make_response(401, body={"detail": "bad token"})])
    with pytest.raises(_AuthError):
        await limiter.request_json(client, "GET", "/x", raise_on_status={401: _AuthError})


# ── network error retry ───────────────────────────────────────────────


async def test_timeout_then_success_recovers():
    limiter = RateLimiter(requests_per_second=1000, max_retries=2, backoff_base=0.001, backoff_jitter=0.0, name="t")
    client = _make_client([
        httpx.TimeoutException("slow"),
        _make_response(200, body={"ok": 1}),
    ])
    out = await limiter.request_json(client, "GET", "/x")
    assert out == {"ok": 1}


async def test_timeout_exhausted_raises_timeout():
    limiter = RateLimiter(requests_per_second=1000, max_retries=1, backoff_base=0.001, backoff_jitter=0.0, name="t")
    client = _make_client([httpx.TimeoutException("a"), httpx.TimeoutException("b")])
    with pytest.raises(httpx.TimeoutException):
        await limiter.request_json(client, "GET", "/x")


# ── circuit breaker ───────────────────────────────────────────────────


async def test_circuit_breaker_opens_after_failures():
    limiter = RateLimiter(
        requests_per_second=1000, max_retries=0, backoff_base=0.001,
        backoff_jitter=0.0, max_consecutive_failures=2, name="t",
    )
    client = _make_client([
        _make_response(429), _make_response(429),
    ])
    # Two 429 calls trip the circuit
    for _ in range(2):
        try:
            await limiter.request_json(client, "GET", "/x")
        except httpx.HTTPStatusError:
            pass
    # Third call refuses to even hit the wire
    with pytest.raises(CircuitOpenError):
        await limiter.acquire()


async def test_circuit_breaker_off_by_default():
    limiter = RateLimiter(requests_per_second=1000, max_retries=0, backoff_base=0.001, backoff_jitter=0.0, name="t")
    client = _make_client([_make_response(429)])
    try:
        await limiter.request_json(client, "GET", "/x")
    except httpx.HTTPStatusError:
        pass
    # Many subsequent failures don't trip anything
    await limiter.acquire()


# ── token bucket throttle ─────────────────────────────────────────────


async def test_throttle_enforces_min_interval():
    limiter = RateLimiter(requests_per_second=10, max_retries=0, backoff_base=0.001, backoff_jitter=0.0, name="t")
    # 3 calls back-to-back should take at least 2 * (1/10s) = 0.2s
    client = _make_client([_make_response(200, body={}) for _ in range(3)])
    start = time.monotonic()
    for _ in range(3):
        await limiter.request_json(client, "GET", "/x")
    elapsed = time.monotonic() - start
    assert elapsed >= 0.18  # generous lower bound for CI


# ── parse helper ──────────────────────────────────────────────────────


def test_parse_retry_after_handles_missing():
    response = _make_response(429)
    assert _parse_retry_after(response) is None


def test_parse_retry_after_handles_bad_value():
    response = _make_response(429, headers={"Retry-After": "soon"})
    assert _parse_retry_after(response) is None


def test_parse_retry_after_handles_numeric():
    response = _make_response(429, headers={"Retry-After": "12.5"})
    assert _parse_retry_after(response) == 12.5


# ── invalid construction ──────────────────────────────────────────────


def test_negative_rate_raises():
    with pytest.raises(ValueError):
        RateLimiter(requests_per_second=0)
