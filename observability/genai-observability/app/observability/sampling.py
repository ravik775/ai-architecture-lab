"""
`X-Force-Trace` support: a header that forces one specific request to be
captured at full fidelity, independent of the ratio/tail-sampling policy
chain everything else goes through.

Design constraints (from the security review this implements):
  - Must not be gate-able by the ratio sampler - if `ParentBased(
    TraceIdRatioBased(...))` could veto it, it wouldn't "guarantee"
    anything. So this wraps the configured sampler and checks first,
    unconditionally, before ever consulting the wrapped sampler.
  - Must not be usable by just anyone - forcing full tracing is also a
    way to force extra Collector/backend load per request, so honoring
    it requires the caller to hold the `force_trace` permission (see
    `app/security/auth.py`). Callers without it still get to send the
    header; it's silently ignored rather than rejected (see
    `app/api/routes.py`) - that's a product decision (don't 403 a
    harmless header), not a limitation of this sampler.
  - Must not touch redaction. This sampler only ever answers "is this
    span recorded and exported," never "what's in it." PII scrubbing
    (Layers 1/2/4 in docs/SECURITY-PLAN.md) runs unconditionally on
    every span this produces, forced or not.
"""
from __future__ import annotations

from opentelemetry import baggage
from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import Decision, Sampler, SamplingResult
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

FORCE_TRACE_BAGGAGE_KEY = "app.force_trace"


class ForceTraceSampler(Sampler):
    """
    Wraps another Sampler. If the `app.force_trace` baggage key is set
    (by `app/api/routes.py`, only after an RBAC permission check), every
    span in this trace is recorded and sampled unconditionally.
    Otherwise, delegates to the wrapped sampler untouched.
    """

    def __init__(self, wrapped: Sampler) -> None:
        self._wrapped = wrapped

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: list[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        if baggage.get_baggage(FORCE_TRACE_BAGGAGE_KEY, context=parent_context) == "true":
            return SamplingResult(
                Decision.RECORD_AND_SAMPLE,
                attributes,
                trace_state,
            )
        return self._wrapped.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )

    def get_description(self) -> str:
        return f"ForceTraceSampler({self._wrapped.get_description()})"


def with_baggage_context(force: bool) -> Context:
    """
    Returns a Context with `app.force_trace` set, based on the current
    context, ready to `context.attach()` before opening the root span.
    `force=False` returns the current context unmodified (no-op).
    """
    from opentelemetry import context as context_api

    current = context_api.get_current()
    if not force:
        return current
    return baggage.set_baggage(FORCE_TRACE_BAGGAGE_KEY, "true", context=current)
