"""AppMetrics instrument recording - app/observability/metrics.py.

Builds a private MeterProvider + InMemoryMetricReader per test (not the
process-wide singleton from get_app_metrics()) so these tests are fully
isolated from each other and from whatever the app/health-monitor tests
do to global OTel state.
"""
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app.health.monitor import WindowSummary
from app.observability.metrics import AppMetrics


def _build() -> tuple[AppMetrics, InMemoryMetricReader]:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")
    return AppMetrics(meter), reader


def _datapoints(reader: InMemoryMetricReader, metric_name: str):
    data = reader.get_metrics_data()
    if data is None:
        return []
    points = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == metric_name:
                    points.extend(m.data.data_points)
    return points


def test_record_chat_request_increments_counter_by_status():
    app_metrics, reader = _build()
    app_metrics.record_chat_request("success")
    app_metrics.record_chat_request("success")
    app_metrics.record_chat_request("error")

    points = _datapoints(reader, "app.chat.requests_total")
    by_status = {dict(p.attributes)["app.status"]: p.value for p in points}
    assert by_status == {"success": 2, "error": 1}


def test_record_llm_call_records_duration_and_token_histograms():
    app_metrics, reader = _build()
    app_metrics.record_llm_call(
        model="openrouter/test-model",
        duration_seconds=0.42,
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.001,
    )

    duration_points = _datapoints(reader, "gen_ai.client.operation.duration")
    assert len(duration_points) == 1
    assert duration_points[0].sum == 0.42
    assert dict(duration_points[0].attributes)["gen_ai.request.model"] == "openrouter/test-model"

    token_points = _datapoints(reader, "gen_ai.client.token.usage")
    by_type = {dict(p.attributes)["gen_ai.token.type"]: p.sum for p in token_points}
    assert by_type == {"input": 10, "output": 5}

    cost_points = _datapoints(reader, "app.llm.cost_usd_total")
    assert cost_points[0].value == 0.001


def test_record_llm_call_skips_zero_or_none_token_counts():
    app_metrics, reader = _build()
    app_metrics.record_llm_call(
        model="m", duration_seconds=0.1, prompt_tokens=None, completion_tokens=0, cost_usd=None
    )
    # duration is always recorded, but no token histogram points and no cost add
    assert len(_datapoints(reader, "gen_ai.client.operation.duration")) == 1
    assert _datapoints(reader, "gen_ai.client.token.usage") == []
    assert _datapoints(reader, "app.llm.cost_usd_total") == []


def test_record_health_summary_updates_counters_and_gauge():
    app_metrics, reader = _build()
    summary = WindowSummary(
        window_start=0.0,
        window_end=60.0,
        total=10,
        success=8,
        failure=2,
        success_rate=0.8,
        latency_avg_ms=1.0,
        latency_min_ms=0.5,
        latency_max_ms=2.0,
        latency_p95_ms=1.8,
    )
    app_metrics.record_health_summary(summary)

    points = _datapoints(reader, "app.health.checks_total")
    by_outcome = {dict(p.attributes)["app.health.outcome"]: p.value for p in points}
    assert by_outcome == {"success": 8, "failure": 2}

    gauge_points = _datapoints(reader, "app.health.success_rate")
    assert gauge_points[0].value == 0.8
