"""Health probe + 1-minute sampling/aggregation - app/health/monitor.py.

Tests call the synchronous helper methods (`_probe_once`, `_flush_summary`)
directly rather than running the real asyncio loop - `start()`/`stop()`
are thin wrappers around the same logic and are exercised end-to-end by
the smoke tests already run manually during development (see README).
"""
import time
from unittest.mock import patch

from app.health.monitor import CheckResult, HealthMonitor


def _monitor(**component_checks) -> HealthMonitor:
    return HealthMonitor(
        interval_seconds=2.0,
        summary_window_seconds=60.0,
        component_checks=component_checks,
    )


# ------------------------------------------------------------- _probe_once --
def test_probe_once_all_checks_pass_is_ok():
    monitor = _monitor(a=lambda: True, b=lambda: True)
    monitor._probe_once()
    assert monitor.last_check.ok is True
    assert monitor.last_check.components == {"a": True, "b": True}
    assert monitor.buffered_count == 1


def test_probe_once_any_check_fails_is_not_ok():
    monitor = _monitor(a=lambda: True, b=lambda: False)
    monitor._probe_once()
    assert monitor.last_check.ok is False


def test_probe_once_check_that_raises_counts_as_failed_not_crashed():
    def boom():
        raise RuntimeError("upstream is down")

    monitor = _monitor(a=boom)
    monitor._probe_once()  # must not raise
    assert monitor.last_check.ok is False
    assert monitor.last_check.components == {"a": False}


def test_probe_once_no_component_checks_defaults_ok():
    monitor = _monitor()
    monitor._probe_once()
    assert monitor.last_check.ok is True


# ----------------------------------------------------------- _flush_summary --
def _fake_metrics_stub():
    """Avoid depending on the global metrics singleton for this unit test."""
    stub = type("Stub", (), {"record_health_summary": lambda self, summary: None})()
    return stub


def test_flush_summary_computes_correct_aggregate_stats():
    monitor = _monitor()
    now = time.time()
    monitor._state.buffer.extend(
        [
            CheckResult(ok=True, latency_ms=10.0, timestamp=now, components={}),
            CheckResult(ok=True, latency_ms=20.0, timestamp=now, components={}),
            CheckResult(ok=False, latency_ms=30.0, timestamp=now, components={}),
            CheckResult(ok=True, latency_ms=40.0, timestamp=now, components={}),
        ]
    )
    with patch("app.health.monitor.get_app_metrics", return_value=_fake_metrics_stub()):
        monitor._flush_summary()

    summary = monitor.last_summary
    assert summary.total == 4
    assert summary.success == 3
    assert summary.failure == 1
    assert summary.success_rate == 0.75
    assert summary.latency_avg_ms == 25.0
    assert summary.latency_min_ms == 10.0
    assert summary.latency_max_ms == 40.0
    # buffer must be drained after a flush - that's the whole "30 checks -> 1 summary" point
    assert monitor.buffered_count == 0


def test_flush_summary_with_empty_buffer_is_a_noop():
    monitor = _monitor()
    with patch("app.health.monitor.get_app_metrics", return_value=_fake_metrics_stub()):
        monitor._flush_summary()
    assert monitor.last_summary is None


def test_flush_summary_p95_uses_nearest_rank():
    monitor = _monitor()
    now = time.time()
    # 20 values: 1..19 plus one outlier (1000). Sorted: [1,2,...,19,1000].
    # p95_index = round(0.95 * (20-1)) = round(18.05) = 18 (0-based) -> value 19,
    # i.e. the outlier at the very top is deliberately excluded by nearest-rank
    # p95 with this sample size - a real property of the estimator, not a bug,
    # and worth pinning down in a test so a future refactor can't change it silently.
    latencies = list(range(1, 20)) + [1000]
    monitor._state.buffer.extend(
        CheckResult(ok=True, latency_ms=float(v), timestamp=now, components={}) for v in latencies
    )
    with patch("app.health.monitor.get_app_metrics", return_value=_fake_metrics_stub()):
        monitor._flush_summary()
    summary = monitor.last_summary
    assert summary.latency_max_ms == 1000.0
    assert summary.latency_p95_ms == 19.0
