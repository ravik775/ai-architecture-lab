"""OpenTelemetry tracing setup: OTLP/HTTP export, configurable sampling,
FastAPI/httpx/SQLAlchemy auto-instrumentation, graceful shutdown.

Metrics deliberately do NOT go through OTel here - see `metrics.py` for
why `/metrics` is a direct `prometheus_client` endpoint instead of a second
OTLP pipeline (avoids running two metrics paths for one demo app).

Sampling is split across two layers on purpose:
- Here (SDK, head sampling): health-check volume control + the RBAC-gated
  force_trace override - decisions that either don't depend on the
  request's outcome, or are an explicit caller override. See
  `HealthCheckRateLimitedSampler`'s docstring.
- The OTel Collector (`docker/otel-collector-config.yaml`'s
  `tail_sampling` processor): "always keep failed-request traces, sample a
  percentage of successful ones" - a decision that can only be made AFTER
  a trace completes, which is why the SDK's own default branch below is
  `ParentBased(ALWAYS_ON)` (forward everything for ordinary traffic) - the
  Collector's `baseline-probabilistic` policy applies the actual ratio to
  non-error traces instead (see `OTEL_TAIL_SAMPLING_BASELINE_PERCENT`).
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.processor.baggage import BaggageSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased

from app.config.settings import ObservabilitySettings, SecuritySettings
from app.observability.context import PROPAGATED_BAGGAGE_KEYS
from app.observability.sampling import HealthCheckRateLimitedSampler

logger = logging.getLogger(__name__)

_tracer_provider: TracerProvider | None = None


def configure_tracing(settings: ObservabilitySettings, security: SecuritySettings) -> TracerProvider:
    """Idempotent-ish: safe to call once per process at startup."""
    global _tracer_provider

    resource = Resource.create({"service.name": settings.service_name})
    sampler = HealthCheckRateLimitedSampler(
        ParentBased(ALWAYS_ON),
        interval_seconds=settings.health_check_sample_interval_seconds,
        jwt_secret=security.jwt_secret,
        jwt_algorithm=security.jwt_algorithm,
        force_trace_role=security.force_trace_role,
    )
    provider = TracerProvider(resource=resource, sampler=sampler)

    # Copies correlation_id/request_id baggage onto every span at start
    # time - not just the root span middleware tags directly - so they're
    # usable as a Tempo TraceQL `select()` column on ANY span (application,
    # httpx, SQLAlchemy), not only the root. See middleware.py/correlation.py
    # for where the baggage is actually set.
    provider.add_span_processor(BaggageSpanProcessor(lambda key: key in PROPAGATED_BAGGAGE_KEYS))

    if settings.otel_enabled:
        exporter: SpanExporter = OTLPSpanExporter(
            endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces"
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    if settings.console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()

    # PydanticAI's own OTel instrumentation (OpenTelemetry GenAI semantic
    # conventions) - covers agent runs, model requests, and tool calls.
    # Applies to every Agent instance process-wide, so it must run once,
    # before any Agent is constructed.
    from pydantic_ai import Agent as _PydanticAgent

    _PydanticAgent.instrument_all()

    _tracer_provider = provider
    return provider


def instrument_fastapi(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy(sync_engine) -> None:  # noqa: ANN001
    SQLAlchemyInstrumentor().instrument(engine=sync_engine)


def get_tracer(name: str = "weather-intelligence-agent") -> trace.Tracer:
    return trace.get_tracer(name)


def shutdown_tracing() -> None:
    global _tracer_provider
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        _tracer_provider = None
