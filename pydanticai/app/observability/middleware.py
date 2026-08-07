"""Request-ID / correlation-ID propagation + HTTP request metrics + a
request-completion log line.

Lives at the ASGI-middleware boundary (framework-adjacent, not business
logic) - it labels metrics by *route template* (e.g. `/v1/weather/current`),
never the raw resolved path or query params, keeping cardinality bounded.
"""
from __future__ import annotations

import logging
import time
import uuid

from opentelemetry import baggage, context as otel_context, trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.observability.context import correlation_id_var, request_id_var
from app.observability.metrics import http_request_duration_seconds, http_requests_total
from app.observability.sampling import FORCE_TRACE_AUTH_BAGGAGE_KEY

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # request_id: always app-generated, identifies this one hop -
        # never client-controlled in practice even though a passed-through
        # header is honored for reverse-proxy setups.
        request_id = request.headers.get(REQUEST_ID_HEADER.lower()) or str(uuid.uuid4())
        # correlation_id: caller-controlled and reusable across many
        # requests/UI actions - defaults to a fresh UUID if not supplied.
        # See `context.py`'s module docstring for the distinction.
        correlation_id = request.headers.get(CORRELATION_ID_HEADER.lower()) or str(uuid.uuid4())

        request_id_token = request_id_var.set(request_id)
        correlation_id_token = correlation_id_var.set(correlation_id)

        # Tag the root span directly (belt-and-suspenders - guaranteed to
        # land even if baggage/task-context propagation ever misbehaves)...
        span = trace.get_current_span()
        span.set_attribute("request_id", request_id)
        span.set_attribute("correlation_id", correlation_id)

        # ...and set OTel baggage so the `BaggageSpanProcessor` (see
        # tracing.py) copies these onto every CHILD span too (httpx,
        # SQLAlchemy, our own weather_service/batch_service spans) -
        # without this, only the root span carries them, and a Tempo
        # TraceQL `select()` on a non-root span comes back empty.
        #
        # `auth_token` (see sampling.py) is deliberately scrubbed out right
        # here rather than carried forward: it only exists in baggage to be
        # visible to the Sampler at span-creation time, which has already
        # happened by the time this middleware runs. Left in place, it
        # would keep riding the OTel Context into this app's own outgoing
        # httpx calls (Open-Meteo, LiteLLM) via the same baggage propagator,
        # leaking a bearer credential to third parties - dropping it here
        # closes that off before any application code executes.
        ctx = baggage.remove_baggage(FORCE_TRACE_AUTH_BAGGAGE_KEY, context=otel_context.get_current())
        ctx = baggage.set_baggage("request_id", request_id, context=ctx)
        ctx = baggage.set_baggage("correlation_id", correlation_id, context=ctx)
        baggage_token = otel_context.attach(ctx)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            otel_context.detach(baggage_token)
            request_id_var.reset(request_id_token)
            correlation_id_var.reset(correlation_id_token)

        duration = time.perf_counter() - started
        route = request.scope.get("route")
        route_template = route.path if route is not None else request.url.path

        http_requests_total.labels(
            method=request.method, route=route_template, status_code=str(response.status_code)
        ).inc()
        http_request_duration_seconds.labels(method=request.method, route=route_template).observe(duration)

        # Request-completion log line: `request_id`/`correlation_id` are
        # picked up automatically by `TraceContextFilter` (see logging.py),
        # so every request - not just errors/batch jobs - now has a
        # correlatable JSON log entry to grep by X-Request-ID or
        # X-Correlation-ID.
        logger.info(
            "request completed",
            extra={
                "http_method": request.method,
                "http_route": route_template,
                "http_status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )

        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
