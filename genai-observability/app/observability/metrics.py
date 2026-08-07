"""
OTel Metrics pipeline, alongside (not instead of) the traces pipeline.

Why metrics in addition to spans: traces answer "what happened in this
one request/session" (great for debugging one user's chat, which is what
Langfuse/LangSmith are built for). Metrics answer "what's the request
rate and token spend across the whole fleet right now" (a timeseries
question, not a per-trace one). Trying to answer the second question by
querying spans works at small scale and falls over once you have real
production volume - hence a dedicated MetricReader alongside the
SpanProcessor, exported on its own OTLP pipeline.

Honest limitation (verified against provider docs, Aug 2026): neither
Langfuse nor LangSmith ingest OTLP *metrics* today - both are trace /
observation stores for LLM apps, not timeseries backends. So:
  - OBSERVABILITY_PROVIDER=collector: metrics go collector -> Prometheus
    (see collector/otel-collector-config.yaml's `metrics` pipeline and
    the bundled `prometheus` service in docker-compose.yml). This is the
    only mode with a real metrics destination.
  - langfuse_direct / langsmith_direct / console: metrics fall back to
    stdout (ConsoleMetricExporter) so nothing crashes and you can still
    see the numbers locally, but nothing is persisted. Switch to
    collector mode if you need a queryable metrics backend.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from app.config import ObservabilityProvider, Settings

logger = logging.getLogger(__name__)


def _build_metric_reader(settings: Settings) -> PeriodicExportingMetricReader:
    provider = settings.observability_provider

    if provider == ObservabilityProvider.COLLECTOR:
        endpoint = f"{settings.otel_exporter_otlp_endpoint.rstrip('/')}/v1/metrics"
        if settings.otel_tls_enabled:
            # Same mTLS identity as the trace exporter (app/observability/setup.py) -
            # one client cert for both OTLP signals over the one app<->collector hop.
            exporter = OTLPMetricExporter(
                endpoint=endpoint,
                certificate_file=settings.otel_tls_ca_file,
                client_certificate_file=settings.otel_tls_client_cert_file,
                client_key_file=settings.otel_tls_client_key_file,
            )
            description = f"OTLP -> collector -> Prometheus, mTLS ({endpoint})"
        else:
            exporter = OTLPMetricExporter(endpoint=endpoint)
            description = f"OTLP -> collector -> Prometheus, plaintext ({endpoint})"
    elif provider in (ObservabilityProvider.LANGFUSE_DIRECT, ObservabilityProvider.LANGSMITH_DIRECT):
        exporter = ConsoleMetricExporter()
        description = (
            f"console (fallback: {provider.value} has no OTLP metrics ingestion - "
            "set OBSERVABILITY_PROVIDER=collector to reach Prometheus)"
        )
    else:
        exporter = ConsoleMetricExporter()
        description = "console (stdout)"

    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=int(settings.metrics_export_interval_seconds * 1000),
    )
    logger.info(
        "Metrics export configured | %s | interval=%ss",
        description,
        settings.metrics_export_interval_seconds,
    )
    return reader


def configure_metrics(settings: Settings) -> MeterProvider:
    """Idempotent-ish (mirrors configure_observability). Call once at startup."""
    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.app_env,
        }
    )
    reader = _build_metric_reader(settings)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return provider


def get_meter(name: str = "genai-observability-service"):
    return metrics.get_meter(name)


class AppMetrics:
    """
    Instrument set covering the two examples called out in the roadmap:
    request rate (`app.chat.requests_total`) and token cost per minute
    (`app.llm.cost_usd_total`, a monotonic counter - rate() it over 60s
    in Prometheus/Grafana to get $/min). Also covers the OTel GenAI
    semantic-convention metric names where they exist, and mirrors the
    health monitor's 1-minute summary as metrics so it's queryable as a
    timeseries too, not just as spans.
    """

    def __init__(self, meter) -> None:
        self.chat_requests_total = meter.create_counter(
            "app.chat.requests_total",
            unit="1",
            description="Total /chat requests, by outcome",
        )
        self.llm_operation_duration = meter.create_histogram(
            "gen_ai.client.operation.duration",
            unit="s",
            description="Duration of litellm completion calls",
        )
        self.llm_token_usage = meter.create_histogram(
            "gen_ai.client.token.usage",
            unit="token",
            description="Prompt/completion tokens per LLM call",
        )
        self.llm_cost_usd_total = meter.create_counter(
            "app.llm.cost_usd_total",
            unit="usd",
            description="Cumulative OpenRouter spend - rate() over 1m for cost/minute",
        )
        self.health_checks_total = meter.create_counter(
            "app.health.checks_total",
            unit="1",
            description="Health probe outcomes (mirrors health.summary_1m span)",
        )

        self._last_success_rate = 1.0
        self.health_success_rate = meter.create_observable_gauge(
            "app.health.success_rate",
            callbacks=[self._observe_success_rate],
            unit="1",
            description="Most recent 1-minute health check success rate",
        )

    def _observe_success_rate(self, options=None) -> Iterable[Observation]:
        yield Observation(self._last_success_rate)

    def record_chat_request(self, status: str) -> None:
        self.chat_requests_total.add(1, {"app.status": status})

    def record_llm_call(
        self,
        *,
        model: str,
        duration_seconds: float,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        cost_usd: float | None,
    ) -> None:
        attrs = {"gen_ai.system": "openrouter", "gen_ai.request.model": model}
        self.llm_operation_duration.record(duration_seconds, attrs)
        if prompt_tokens:
            self.llm_token_usage.record(prompt_tokens, {**attrs, "gen_ai.token.type": "input"})
        if completion_tokens:
            self.llm_token_usage.record(completion_tokens, {**attrs, "gen_ai.token.type": "output"})
        if cost_usd:
            self.llm_cost_usd_total.add(cost_usd, attrs)

    def record_health_summary(self, summary) -> None:
        self.health_checks_total.add(summary.success, {"app.health.outcome": "success"})
        self.health_checks_total.add(summary.failure, {"app.health.outcome": "failure"})
        self._last_success_rate = summary.success_rate


_app_metrics: AppMetrics | None = None


def get_app_metrics() -> AppMetrics:
    """
    Lazily builds the instrument set against whatever MeterProvider is
    globally active. Must be called for the first time only after
    `configure_metrics()` has run (i.e. not at import time) - every
    call-site in this codebase calls it inside a request/loop, never at
    module scope, for exactly that reason.
    """
    global _app_metrics
    if _app_metrics is None:
        _app_metrics = AppMetrics(get_meter())
    return _app_metrics
