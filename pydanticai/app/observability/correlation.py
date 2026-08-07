"""UI-side counterpart to what `RequestContextMiddleware` does for HTTP
requests: NiceGUI callbacks call `app.state.*` services in-process, so
there's no header to carry a correlation ID - `correlation_scope` sets the
same contextvar, attaches OTel baggage (so the `BaggageSpanProcessor` in
tracing.py copies it onto every span this action creates, not just the
root), and opens a span tagged with it - so a UI-triggered action is
traceable/greppable by the same correlation ID the user sees in the UI.

`force_trace`/`auth_token` let a UI action opt into the same RBAC-gated
force-trace override REST callers get via the `baggage` header (see
`app/observability/sampling.py`) - the "Trace" checkbox in pages.py wires
this up for a logged-in trace_admin user. Same leak concern applies here as
in `RequestContextMiddleware`: `auth_token` is scrubbed from the context
immediately after the span is created (once `should_sample()` has already
run and used it), so it never rides along into this action's own outgoing
httpx calls (Open-Meteo/LiteLLM).
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import baggage, context as otel_context

from app.observability.context import correlation_id_var
from app.observability.sampling import FORCE_TRACE_AUTH_BAGGAGE_KEY, FORCE_TRACE_BAGGAGE_KEY
from app.observability.tracing import get_tracer

tracer = get_tracer(__name__)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


@contextmanager
def correlation_scope(
    correlation_id: str, span_name: str, *, force_trace: bool = False, auth_token: str | None = None
) -> Iterator[None]:
    correlation_id = correlation_id or new_correlation_id()
    contextvar_token = correlation_id_var.set(correlation_id)

    sampling_ctx = baggage.set_baggage("correlation_id", correlation_id)
    if force_trace and auth_token:
        sampling_ctx = baggage.set_baggage(FORCE_TRACE_BAGGAGE_KEY, "true", context=sampling_ctx)
        sampling_ctx = baggage.set_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY, auth_token, context=sampling_ctx)

    try:
        sampling_token = otel_context.attach(sampling_ctx)
        try:
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("correlation_id", correlation_id)
                scrub_ctx = baggage.remove_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY, context=otel_context.get_current())
                scrub_token = otel_context.attach(scrub_ctx)
                try:
                    yield
                finally:
                    otel_context.detach(scrub_token)
        finally:
            otel_context.detach(sampling_token)
    finally:
        correlation_id_var.reset(contextvar_token)
