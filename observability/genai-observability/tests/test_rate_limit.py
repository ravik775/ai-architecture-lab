"""
Unit tests for app/security/rate_limit.py's TokenBucketRateLimiter and the
get_rate_limiter() singleton factory. Uses a fake monotonic clock so refill
behavior is deterministic and doesn't depend on real elapsed wall time.
"""
import pytest
from fastapi import HTTPException

from app.security import rate_limit as rl


# ------------------------------------------------------------- TokenBucket --
def test_first_requests_up_to_capacity_succeed(monkeypatch):
    monkeypatch.setattr(rl.time, "monotonic", lambda: 1000.0)
    limiter = rl.TokenBucketRateLimiter(requests_per_minute=60, capacity=5)
    for _ in range(5):
        limiter.check("k1")  # should not raise


def test_request_beyond_capacity_raises_429(monkeypatch):
    monkeypatch.setattr(rl.time, "monotonic", lambda: 1000.0)
    limiter = rl.TokenBucketRateLimiter(requests_per_minute=60, capacity=3)
    for _ in range(3):
        limiter.check("k1")
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("k1")
    assert exc_info.value.status_code == 429


def test_429_includes_retry_after_header(monkeypatch):
    monkeypatch.setattr(rl.time, "monotonic", lambda: 1000.0)
    limiter = rl.TokenBucketRateLimiter(requests_per_minute=60, capacity=1)
    limiter.check("k1")
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("k1")
    assert "Retry-After" in exc_info.value.headers
    assert int(exc_info.value.headers["Retry-After"]) >= 1


def test_bucket_refills_over_time(monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: now["t"])

    # 60 req/min = 1 token/sec, capacity 2.
    limiter = rl.TokenBucketRateLimiter(requests_per_minute=60, capacity=2)
    limiter.check("k1")
    limiter.check("k1")
    with pytest.raises(HTTPException):
        limiter.check("k1")  # exhausted

    now["t"] += 1.5  # ~1.5 tokens refilled
    limiter.check("k1")  # should succeed now


def test_different_keys_have_independent_buckets(monkeypatch):
    monkeypatch.setattr(rl.time, "monotonic", lambda: 1000.0)
    limiter = rl.TokenBucketRateLimiter(requests_per_minute=60, capacity=1)
    limiter.check("key-a")
    with pytest.raises(HTTPException):
        limiter.check("key-a")
    limiter.check("key-b")  # separate bucket, unaffected by key-a's exhaustion


def test_reset_clears_all_bucket_state(monkeypatch):
    monkeypatch.setattr(rl.time, "monotonic", lambda: 1000.0)
    limiter = rl.TokenBucketRateLimiter(requests_per_minute=60, capacity=1)
    limiter.check("k1")
    with pytest.raises(HTTPException):
        limiter.check("k1")
    limiter.reset()
    limiter.check("k1")  # bucket rebuilt fresh, succeeds


def test_default_capacity_is_requests_per_minute_when_unspecified():
    limiter = rl.TokenBucketRateLimiter(requests_per_minute=45)
    assert limiter.capacity == 45


def test_default_capacity_floors_at_one_for_low_rates():
    limiter = rl.TokenBucketRateLimiter(requests_per_minute=0.1)
    assert limiter.capacity == 1.0


# ------------------------------------------------------------ get_rate_limiter --
@pytest.fixture(autouse=True)
def _reset_singleton():
    rl._limiter = None
    rl._limiter_rate = None
    yield
    rl._limiter = None
    rl._limiter_rate = None


def test_get_rate_limiter_disabled_when_rate_non_positive():
    assert rl.get_rate_limiter(0) is None
    assert rl.get_rate_limiter(-5) is None


def test_get_rate_limiter_returns_singleton_for_same_rate():
    a = rl.get_rate_limiter(30)
    b = rl.get_rate_limiter(30)
    assert a is b


def test_get_rate_limiter_rebuilds_when_rate_changes():
    a = rl.get_rate_limiter(30)
    b = rl.get_rate_limiter(60)
    assert a is not b
    assert b.rate_per_second == 1.0
