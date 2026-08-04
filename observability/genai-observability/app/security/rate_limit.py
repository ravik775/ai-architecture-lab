"""
Basic request-rate guardrail on `/chat` - this is the specific gap the
risk register (README "Security") flagged repeatedly and left open:
API-key auth controls *who* can call `/chat`, this controls *how often*.
Distinct from the Collector's `tail_sampling` `rate_limiting` policy,
which protects the observability pipeline from trace-volume spikes, not
OpenRouter spend from request-volume spikes - the two are unrelated
budgets on unrelated resources.

Deliberately simple: an in-memory token bucket per API-key `key_id`, no
Redis, no distributed state - matching this service's "keep it simple"
brief and its single-container deployment shape. Swap for a shared
(Redis-backed) limiter before running more than one app replica, since
each replica would otherwise enforce its own independent budget and the
effective limit becomes `rate_limit_requests_per_minute * replica_count`.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, status


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class TokenBucketRateLimiter:
    """
    Classic token bucket: `capacity` tokens available immediately (burst
    allowance), refilled continuously at `requests_per_minute / 60`
    tokens/second. One bucket per key, created lazily on first use.
    """

    def __init__(self, *, requests_per_minute: float, capacity: float | None = None) -> None:
        self.rate_per_second = requests_per_minute / 60.0
        self.capacity = capacity if capacity is not None else max(1.0, requests_per_minute)
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """
        Raises HTTPException(429) if `key` has no budget left; otherwise
        consumes one token and returns normally. Thread-safe (FastAPI can
        run sync dependencies in a thread pool).
        """
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, last_refill=now)
                self._buckets[key] = bucket

            elapsed = now - bucket.last_refill
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.rate_per_second)
            bucket.last_refill = now

            if bucket.tokens < 1.0:
                retry_after = 1
                if self.rate_per_second > 0:
                    retry_after = max(1, int((1.0 - bucket.tokens) / self.rate_per_second) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded for this API key - slow down and retry shortly.",
                    headers={"Retry-After": str(retry_after)},
                )

            bucket.tokens -= 1.0

    def reset(self) -> None:
        """Test hook - clears all bucket state."""
        with self._lock:
            self._buckets.clear()


_limiter: TokenBucketRateLimiter | None = None
_limiter_rate: float | None = None


def get_rate_limiter(requests_per_minute: float) -> TokenBucketRateLimiter | None:
    """
    Lazily builds (or rebuilds, if the configured rate changed) the
    process-wide limiter singleton. Returns None if rate limiting is
    disabled (`requests_per_minute <= 0`).
    """
    global _limiter, _limiter_rate
    if requests_per_minute <= 0:
        return None
    if _limiter is None or _limiter_rate != requests_per_minute:
        _limiter = TokenBucketRateLimiter(requests_per_minute=requests_per_minute)
        _limiter_rate = requests_per_minute
    return _limiter
