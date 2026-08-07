"""Process-wide contextvars threaded into structured logs (never into
metric labels - see `metrics.py` cardinality note).

`request_id` vs `correlation_id`: `request_id` is generated fresh by this
app for every single HTTP request/UI action and is never client-supplied -
it identifies one hop. `correlation_id` is meant to span multiple hops/
actions at the caller's discretion: it defaults to an auto-generated UUID
but a caller (REST client via the `X-Correlation-ID` header, or a UI user
via the Correlation ID field) can override it with their own value and
reuse it across several requests to group them in traces/logs.
"""
from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
job_id_var: ContextVar[str] = ContextVar("job_id", default="")

# Baggage keys copied onto EVERY span in a trace (root and children alike)
# by the `BaggageSpanProcessor` registered in `tracing.py` - deliberately
# a closed allowlist, not "copy all baggage", so nothing unexpected ends
# up on spans just because some caller set arbitrary baggage.
PROPAGATED_BAGGAGE_KEYS = frozenset({"correlation_id", "request_id"})
