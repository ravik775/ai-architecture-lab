from app.ai.models import TokenUsage
from app.config import settings


_meter = None
_llm_success_counter = None
_llm_failure_counter = None
_validation_failure_counter = None
_retry_counter = None
_token_counter = None
_cost_counter = None
_latency_histogram = None


class _NoOpInstrument:
    def add(self, value, attributes=None) -> None:
        return None

    def record(self, value, attributes=None) -> None:
        return None


def configure_metrics() -> None:
    global _meter

    if not settings.observability.metrics_enabled:
        return
    if _meter is not None:
        return

    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter,
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        _initialize_noop_instruments()
        return

    readers = []
    if settings.observability.console_metric_exporter_enabled:
        readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))

    metrics.set_meter_provider(
        MeterProvider(
            metric_readers=readers,
            resource=Resource.create({"service.name": "expense-ai"}),
        )
    )
    _meter = metrics.get_meter("expense-ai")
    _initialize_instruments()


def record_llm_success(provider: str, model: str, latency_ms: float) -> None:
    _ensure_initialized()
    labels = {"provider": str(provider), "model": model}
    _llm_success_counter.add(1, labels)
    _latency_histogram.record(latency_ms, labels)


def record_llm_failure(provider: str, model: str, error_type: str) -> None:
    _ensure_initialized()
    _llm_failure_counter.add(
        1,
        {"provider": str(provider), "model": model, "error_type": error_type},
    )


def record_validation_failure(provider: str, model: str) -> None:
    _ensure_initialized()
    _validation_failure_counter.add(
        1,
        {"provider": str(provider), "model": model},
    )


def record_retry(provider: str, model: str, reason: str) -> None:
    _ensure_initialized()
    _retry_counter.add(
        1,
        {"provider": str(provider), "model": model, "reason": reason},
    )


def record_token_usage(provider: str, model: str, usage: TokenUsage | None) -> None:
    if usage is None:
        return
    _ensure_initialized()
    labels = {"provider": provider, "model": model, }
    for token_type, value in usage.items().items():
        _token_counter.add(value, {**labels, "token_type": token_type}, )


def record_cost(provider: str, model: str, cost_usd: float | None) -> None:
    if cost_usd is None:
        return
    _ensure_initialized()
    _cost_counter.add(cost_usd,  {"provider": str(provider), "model": model, "currency": "USD"},)


def _initialize_instruments() -> None:
    global _llm_success_counter
    global _llm_failure_counter
    global _validation_failure_counter
    global _retry_counter
    global _token_counter
    global _cost_counter
    global _latency_histogram

    meter = _get_meter()
    _llm_success_counter = meter.create_counter("llm_success_total")
    _llm_failure_counter = meter.create_counter("llm_failure_total")
    _validation_failure_counter = meter.create_counter("llm_validation_failure_total")
    _retry_counter = meter.create_counter("llm_retry_total")
    _token_counter = meter.create_counter("llm_token_usage_total")
    _cost_counter = meter.create_counter("llm_estimated_cost_usd_total")
    _latency_histogram = meter.create_histogram("llm_latency_ms")


def _ensure_initialized() -> None:
    global _meter
    if _meter is None:
        try:
            from opentelemetry import metrics
        except ImportError:
            _initialize_noop_instruments()
            return

        _meter = metrics.get_meter("expense-ai")
    if _llm_success_counter is None:
        _initialize_instruments()


def _get_meter():
    global _meter
    if _meter is None:
        try:
            from opentelemetry import metrics
        except ImportError:
            _initialize_noop_instruments()
            return None

        _meter = metrics.get_meter("expense-ai")
    return _meter


def _initialize_noop_instruments() -> None:
    global _llm_success_counter
    global _llm_failure_counter
    global _validation_failure_counter
    global _retry_counter
    global _token_counter
    global _cost_counter
    global _latency_histogram

    noop = _NoOpInstrument()
    _llm_success_counter = noop
    _llm_failure_counter = noop
    _validation_failure_counter = noop
    _retry_counter = noop
    _token_counter = noop
    _cost_counter = noop
    _latency_histogram = noop