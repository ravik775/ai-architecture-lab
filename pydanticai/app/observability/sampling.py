"""Custom sampler: rate-limits health-check traces, with an RBAC-gated
force-trace override.

`/health/live` and `/health/ready` are polled far more often than any real
business traffic (container healthchecks, k8s probes, uptime monitors) and
carry almost no diagnostic value per-call - exporting a trace for every one
would flood the tracing backend for nothing. Everything else keeps using
the configured `TraceIdRatioBased` sampler untouched.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Sequence

import jwt
from opentelemetry import baggage
from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import Decision, Sampler, SamplingResult
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

HEALTH_CHECK_ROUTES = frozenset({"/health/live", "/health/ready"})

# W3C `baggage` header key a caller can set to force-sample a single
# request regardless of route or rate limit, e.g.:
#   curl -H "baggage: force_trace=true,auth_token=<jwt>" http://localhost:8000/health/live
# This is the standards-based equivalent of a custom "force trace" header -
# a genuinely custom header name can't hook into the sampling *decision*
# itself: verified against the installed ASGI instrumentation's source,
# custom-header capture (OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST)
# adds the header to the span *after* the sampler has already run, too late
# to influence it. `baggage` is different: the SDK's default propagator
# extracts it into the parent Context *before* the sampler runs, which is
# exactly the hook point a sampling decision needs.
FORCE_TRACE_BAGGAGE_KEY = "force_trace"

# For the same reason `force_trace` has to travel via baggage instead of a
# custom header, RBAC-checking it has to happen *inside* `should_sample()`
# too - by the time any FastAPI dependency or Starlette middleware runs
# (including the usual `Authorization: Bearer <jwt>` check in
# `app/api/deps.py`), the span already exists and the sampling decision is
# final. So a caller who wants force_trace honored has to put their JWT in
# baggage as well, under this key - unusual compared to a normal bearer
# header, but it's the only value visible at `should_sample()` time.
# `RequestContextMiddleware` scrubs this key out of baggage immediately
# after span creation (see middleware.py) precisely so it never survives
# into this app's own outgoing httpx calls to Open-Meteo/LiteLLM.
FORCE_TRACE_AUTH_BAGGAGE_KEY = "auth_token"

# Attribute key holding the raw request path, checked under both the
# default and newer OTel HTTP semantic-convention names so this doesn't
# silently stop working if semconv stability mode ever changes.
_PATH_ATTRIBUTE_KEYS = ("http.target", "url.path")


def _is_force_trace(parent_context: Context | None) -> bool:
    value = baggage.get_baggage(FORCE_TRACE_BAGGAGE_KEY, parent_context)
    return str(value).strip().lower() == "true"


def _request_path(attributes: Attributes) -> str | None:
    if not attributes:
        return None
    for key in _PATH_ATTRIBUTE_KEYS:
        value = attributes.get(key)
        if value:
            return str(value)
    return None


class HealthCheckRateLimitedSampler(Sampler):
    """Wraps `default_sampler`, intercepting only health-check routes.

    Note on "always sample failed requests": that policy is deliberately
    NOT implemented here. `should_sample()` runs at span-*start* time,
    before the handler has run - the eventual HTTP status/exception is
    unknowable yet, so no head sampler (this one or any other) can
    correctly decide "export only if this turns out to fail". That's what
    tail sampling is for: this app's default (non-health-check) branch is
    wired to `ParentBased(ALWAYS_ON)` (see `configure_tracing()`), and the
    OTel Collector's `tail_sampling` processor (`docker/otel-collector-config.yaml`)
    makes the real keep/drop decision after each trace completes - 100% for
    any trace containing an ERROR-status span, a configurable percentage
    otherwise. Health-check routes are the one exception: they're
    rate-limited right here at the SDK specifically to avoid ever sending
    near-zero-value routine-polling spans to the collector at all -
    including failing ones, since a health check flapping between 200/503
    every few seconds is still "routine polling" for this app's purposes,
    not an application error worth guaranteeing.
    """

    def __init__(
        self,
        default_sampler: Sampler,
        *,
        interval_seconds: float,
        jwt_secret: str,
        jwt_algorithm: str = "HS256",
        force_trace_role: str = "trace_admin",
        health_check_routes: frozenset[str] = HEALTH_CHECK_ROUTES,
    ) -> None:
        self._default_sampler = default_sampler
        self._interval_seconds = interval_seconds
        self._jwt_secret = jwt_secret
        self._jwt_algorithm = jwt_algorithm
        self._force_trace_role = force_trace_role
        self._health_check_routes = health_check_routes
        self._last_sampled_monotonic: float = float("-inf")
        self._lock = threading.Lock()

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        if _is_force_trace(parent_context) and self._has_force_trace_privilege(parent_context):
            # `force_traced=True` lets the OTel Collector's tail_sampling
            # processor (docker/otel-collector-config.yaml) guarantee this
            # trace is kept too - RECORD_AND_SAMPLE here only sets this
            # span's own sampled flag, which the tail sampler does NOT
            # treat as authoritative (it re-decides per trace from
            # scratch); without this attribute, a force-traced span could
            # still be silently dropped by a baseline percentage below
            # 100%, which would make the "force" in force_trace a lie.
            forced_attributes = {**(attributes or {}), "force_traced": True}
            return SamplingResult(Decision.RECORD_AND_SAMPLE, forced_attributes, trace_state)

        if _request_path(attributes) in self._health_check_routes:
            decision = Decision.RECORD_AND_SAMPLE if self._acquire_rate_limit_slot() else Decision.DROP
            return SamplingResult(decision, attributes, trace_state)

        return self._default_sampler.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )

    def _has_force_trace_privilege(self, parent_context: Context | None) -> bool:
        """RBAC gate: `force_trace=true` alone is not enough - the caller
        also has to carry a JWT (see FORCE_TRACE_AUTH_BAGGAGE_KEY's
        docstring above for why it travels via baggage) whose `role` claim
        matches `force_trace_role`. Any failure (missing token, bad
        signature, expired, wrong role) silently falls through to normal
        sampling - a sampling decision must never raise."""
        token = baggage.get_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY, parent_context)
        if not token:
            return False
        try:
            claims = jwt.decode(str(token), self._jwt_secret, algorithms=[self._jwt_algorithm])
        except jwt.PyJWTError:
            return False
        return claims.get("role") == self._force_trace_role

    def _acquire_rate_limit_slot(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if now - self._last_sampled_monotonic >= self._interval_seconds:
                self._last_sampled_monotonic = now
                return True
            return False

    def get_description(self) -> str:
        return (
            f"HealthCheckRateLimitedSampler(interval={self._interval_seconds}s, "
            f"routes={sorted(self._health_check_routes)}, "
            f"force_trace_role={self._force_trace_role}, "
            f"wraps={self._default_sampler.get_description()})"
        )
