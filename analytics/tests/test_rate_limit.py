"""Unit tests for the lightweight local API rate-limiting guard."""

from __future__ import annotations

from farmeasy_mandi_analytics.api.rate_limit import SlidingWindowRateLimiter


def test_sliding_window_releases_capacity_after_its_window() -> None:
    current_time = 100.0
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60, clock=lambda: current_time)

    assert limiter.check("client").allowed is True
    assert limiter.check("client").remaining == 0
    blocked = limiter.check("client")
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 60

    current_time += 60
    refreshed = limiter.check("client")
    assert refreshed.allowed is True
    assert refreshed.remaining == 1


def test_zero_limit_explicitly_disables_the_local_guard() -> None:
    limiter = SlidingWindowRateLimiter(limit=0)

    assert limiter.check("client").allowed is True
    assert limiter.check("client").remaining is None
