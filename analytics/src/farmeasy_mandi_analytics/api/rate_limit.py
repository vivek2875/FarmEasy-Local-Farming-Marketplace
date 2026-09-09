"""Small dependency-free rate limiting for a single analytics API process."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from secrets import compare_digest
from threading import Lock
from time import monotonic

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Result of checking one client against the in-memory sliding window."""

    allowed: bool
    remaining: int | None
    retry_after_seconds: int | None


class SlidingWindowRateLimiter:
    """Thread-safe, per-process rate limiter.

    It deliberately trusts only the direct ASGI client address. A public,
    horizontally scaled deployment should retain this guard and add an
    API-gateway or shared-store limiter in front of it.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int = 60,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if limit < 0:
            raise ValueError("Rate-limit value cannot be negative.")
        if window_seconds < 1:
            raise ValueError("Rate-limit window must be at least one second.")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, client_key: str) -> RateLimitDecision:
        """Consume one request slot, returning a deterministic retry value."""
        if self.limit == 0:
            return RateLimitDecision(allowed=True, remaining=None, retry_after_seconds=None)

        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            requests = self._requests.setdefault(client_key, deque())
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.limit:
                retry_after = max(1, ceil(self.window_seconds - (now - requests[0])))
                return RateLimitDecision(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=retry_after,
                )
            requests.append(now)
            return RateLimitDecision(
                allowed=True,
                remaining=self.limit - len(requests),
                retry_after_seconds=None,
            )


class AnalyticsRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate and optional server-to-server token checks to analytics routes."""

    def __init__(
        self,
        app,
        *,
        limiter: SlidingWindowRateLimiter,
        access_token: str | None = None,
    ) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.access_token = access_token

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/analytics"):
            return await call_next(request)

        client_key = request.client.host if request.client else "unknown-client"
        decision = self.limiter.check(client_key)
        if not decision.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many analytics requests. Try again shortly.",
                        "details": [
                            {
                                "field": "request",
                                "message": (
                                    f"Retry after {decision.retry_after_seconds} second(s)."
                                ),
                            }
                        ],
                    }
                },
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )

        if self.access_token is not None:
            supplied_token = request.headers.get("X-Analytics-Token", "")
            if not compare_digest(supplied_token, self.access_token):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "authentication_required",
                            "message": "A valid analytics service token is required.",
                        }
                    },
                )

        response = await call_next(request)
        if decision.remaining is not None:
            response.headers["X-RateLimit-Limit"] = str(self.limiter.limit)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        return response
