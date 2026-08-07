from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
from opentelemetry import baggage
from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, Decision, Sampler, SamplingResult
from opentelemetry.trace import SpanKind

from app.observability.sampling import FORCE_TRACE_AUTH_BAGGAGE_KEY, HealthCheckRateLimitedSampler

JWT_SECRET = "test-secret-at-least-32-bytes-long-xxxx"
JWT_ALGORITHM = "HS256"
FORCE_TRACE_ROLE = "trace_admin"


class _SpySampler(Sampler):
    """Records whether it was called, so tests can assert delegation."""

    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        self.called = False

    def should_sample(self, parent_context, trace_id, name, kind=None, attributes=None, links=None, trace_state=None):
        self.called = True
        return SamplingResult(self.decision, attributes, trace_state)

    def get_description(self) -> str:
        return "SpySampler"


def _sampler(default: Sampler = ALWAYS_OFF, *, interval_seconds: float = 300.0) -> HealthCheckRateLimitedSampler:
    return HealthCheckRateLimitedSampler(
        default,
        interval_seconds=interval_seconds,
        jwt_secret=JWT_SECRET,
        jwt_algorithm=JWT_ALGORITHM,
        force_trace_role=FORCE_TRACE_ROLE,
    )


def _token(*, role: str = FORCE_TRACE_ROLE, secret: str = JWT_SECRET, expired: bool = False) -> str:
    now = datetime.now(timezone.utc)
    exp = now - timedelta(minutes=5) if expired else now + timedelta(minutes=5)
    return jwt.encode({"sub": "tester", "role": role, "exp": exp}, secret, algorithm=JWT_ALGORITHM)


def _force_trace_context(*, token: str | None) -> Context:
    ctx = baggage.set_baggage("force_trace", "true")
    if token is not None:
        ctx = baggage.set_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY, token, context=ctx)
    return ctx


def _sample(sampler: Sampler, *, path: str | None, context: Context | None = None) -> SamplingResult:
    attributes = {"http.target": path} if path else {}
    return sampler.should_sample(
        context, trace_id=123, name="test", kind=SpanKind.SERVER, attributes=attributes
    )


def test_non_health_check_route_delegates_to_default_sampler():
    default = _SpySampler(Decision.RECORD_AND_SAMPLE)
    sampler = _sampler(default)

    result = _sample(sampler, path="/v1/weather/current")

    assert default.called is True
    assert result.decision == Decision.RECORD_AND_SAMPLE


def test_health_check_route_samples_first_call():
    sampler = _sampler()

    result = _sample(sampler, path="/health/live")

    assert result.decision == Decision.RECORD_AND_SAMPLE


def test_health_check_route_rate_limited_on_immediate_second_call():
    sampler = _sampler()

    first = _sample(sampler, path="/health/live")
    second = _sample(sampler, path="/health/ready")  # different health route, same rate-limit bucket

    assert first.decision == Decision.RECORD_AND_SAMPLE
    assert second.decision == Decision.DROP


def test_health_check_route_samples_again_after_interval_elapses():
    sampler = _sampler(interval_seconds=0.05)

    first = _sample(sampler, path="/health/live")
    time.sleep(0.1)
    second = _sample(sampler, path="/health/live")

    assert first.decision == Decision.RECORD_AND_SAMPLE
    assert second.decision == Decision.RECORD_AND_SAMPLE


def test_force_trace_with_valid_privileged_token_overrides_health_check_rate_limit():
    sampler = _sampler()
    _sample(sampler, path="/health/live")  # consume the rate-limit slot

    ctx = _force_trace_context(token=_token(role=FORCE_TRACE_ROLE))
    forced = _sample(sampler, path="/health/live", context=ctx)

    assert forced.decision == Decision.RECORD_AND_SAMPLE


def test_force_trace_with_valid_privileged_token_overrides_default_sampler_too():
    default = _SpySampler(Decision.DROP)
    sampler = _sampler(default)

    ctx = _force_trace_context(token=_token(role=FORCE_TRACE_ROLE))
    result = _sample(sampler, path="/v1/weather/current", context=ctx)

    assert default.called is False
    assert result.decision == Decision.RECORD_AND_SAMPLE


def test_force_trace_without_any_token_does_not_override():
    sampler = _sampler()
    _sample(sampler, path="/health/live")  # consume the rate-limit slot

    ctx = _force_trace_context(token=None)
    result = _sample(sampler, path="/health/live", context=ctx)

    assert result.decision == Decision.DROP


def test_force_trace_with_wrong_role_does_not_override():
    sampler = _sampler()
    _sample(sampler, path="/health/live")  # consume the rate-limit slot

    ctx = _force_trace_context(token=_token(role="user"))
    result = _sample(sampler, path="/health/live", context=ctx)

    assert result.decision == Decision.DROP


def test_force_trace_with_expired_token_does_not_override():
    sampler = _sampler()
    _sample(sampler, path="/health/live")  # consume the rate-limit slot

    ctx = _force_trace_context(token=_token(role=FORCE_TRACE_ROLE, expired=True))
    result = _sample(sampler, path="/health/live", context=ctx)

    assert result.decision == Decision.DROP


def test_force_trace_with_token_signed_by_wrong_secret_does_not_override():
    sampler = _sampler()
    _sample(sampler, path="/health/live")  # consume the rate-limit slot

    ctx = _force_trace_context(token=_token(role=FORCE_TRACE_ROLE, secret="a-different-32-byte-secret-value-yyyy"))
    result = _sample(sampler, path="/health/live", context=ctx)

    assert result.decision == Decision.DROP


def test_force_trace_baggage_requires_exact_true_value():
    sampler = _sampler()
    _sample(sampler, path="/health/live")  # consume the rate-limit slot

    for bogus_value in ("false", "1", "yes", ""):
        ctx = baggage.set_baggage("force_trace", bogus_value)
        ctx = baggage.set_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY, _token(role=FORCE_TRACE_ROLE), context=ctx)
        result = _sample(sampler, path="/health/live", context=ctx)
        assert result.decision == Decision.DROP, f"value {bogus_value!r} should not force-trace"
