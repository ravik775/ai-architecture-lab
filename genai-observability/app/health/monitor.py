"""
Health monitoring with sampling to keep logs/traces quiet.

Requirement recap:
  - The health probe itself runs every 2s (fast enough for a load
    balancer / k8s liveness-style cadence).
  - We do NOT emit a log line or a span for every single 2s check -
    at 30 checks/minute that's pure noise in a production observability
    backend and inflates Langfuse/LangSmith ingestion cost for zero
    signal. Instead we buffer results in memory and flush ONE aggregated
    summary (count, success rate, latency min/avg/p95/max) every 60s as
    a single span + a single INFO log line.
  - A failure is still surfaced immediately at DEBUG/WARNING locally
    (not exported as its own span) so you can `docker logs` your way to
    a live incident without waiting for the next summary window.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import statistics
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from opentelemetry.trace import SpanKind

from app.observability.metrics import get_app_metrics
from app.observability.tracing import traced_span

logger = logging.getLogger("app.health")


@dataclass
class CheckResult:
    ok: bool
    latency_ms: float
    timestamp: float
    components: dict[str, bool]


@dataclass
class WindowSummary:
    window_start: float
    window_end: float
    total: int
    success: int
    failure: int
    success_rate: float
    latency_avg_ms: float
    latency_min_ms: float
    latency_max_ms: float
    latency_p95_ms: float


@dataclass
class _State:
    last_check: CheckResult | None = None
    last_summary: WindowSummary | None = None
    buffer: deque[CheckResult] = field(default_factory=deque)


ComponentCheck = Callable[[], bool]


class HealthMonitor:
    """Background poller. Call `start()`/`stop()` from the app lifespan."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        summary_window_seconds: float,
        component_checks: dict[str, ComponentCheck] | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds
        self.summary_window_seconds = summary_window_seconds
        self.component_checks = component_checks or {}
        self._state = _State()
        self._task: asyncio.Task | None = None
        self._window_started_at = time.time()
        self._stopping = asyncio.Event()

    # -- public API used by API routes --------------------------------
    @property
    def last_check(self) -> CheckResult | None:
        return self._state.last_check

    @property
    def last_summary(self) -> WindowSummary | None:
        return self._state.last_summary

    @property
    def buffered_count(self) -> int:
        return len(self._state.buffer)

    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._run_loop(), name="health-monitor")
            logger.info(
                "Health monitor started | interval=%ss | summary_window=%ss",
                self.interval_seconds,
                self.summary_window_seconds,
            )

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            await asyncio.wait_for(self._task, timeout=self.interval_seconds + 2)
            self._task = None

    # -- internals -------------------------------------------------------
    async def _run_loop(self) -> None:
        self._window_started_at = time.time()
        while not self._stopping.is_set():
            self._probe_once()
            if time.time() - self._window_started_at >= self.summary_window_seconds:
                self._flush_summary()
            # TimeoutError here just means "no stop signal yet" - the normal
            # tick, not a failure - so suppressing it entirely is correct,
            # not sloppy error handling.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval_seconds)

    def _probe_once(self) -> None:
        start = time.perf_counter()
        components: dict[str, bool] = {}
        for name, check in self.component_checks.items():
            try:
                components[name] = bool(check())
            except Exception:  # noqa: BLE001
                components[name] = False
        ok = all(components.values()) if components else True
        latency_ms = round((time.perf_counter() - start) * 1000, 3)

        result = CheckResult(ok=ok, latency_ms=latency_ms, timestamp=time.time(), components=components)
        self._state.last_check = result
        self._state.buffer.append(result)

        if not ok:
            # Immediate local visibility for failures only - not exported
            # per-check, keeps the noise budget for real incidents.
            logger.warning("Health check failed | components=%s", components)
        else:
            logger.debug("Health check ok | latency_ms=%s", latency_ms)

    def _flush_summary(self) -> None:
        buffer = list(self._state.buffer)
        self._state.buffer.clear()
        window_end = time.time()

        if not buffer:
            self._window_started_at = window_end
            return

        latencies = [r.latency_ms for r in buffer]
        success = sum(1 for r in buffer if r.ok)
        total = len(buffer)
        sorted_latencies = sorted(latencies)
        p95_index = min(len(sorted_latencies) - 1, int(round(0.95 * (len(sorted_latencies) - 1))))

        summary = WindowSummary(
            window_start=self._window_started_at,
            window_end=window_end,
            total=total,
            success=success,
            failure=total - success,
            success_rate=round(success / total, 4),
            latency_avg_ms=round(statistics.fmean(latencies), 3),
            latency_min_ms=round(min(latencies), 3),
            latency_max_ms=round(max(latencies), 3),
            latency_p95_ms=round(sorted_latencies[p95_index], 3),
        )
        self._state.last_summary = summary
        self._window_started_at = window_end

        # Mirror the summary as metrics too (counter + gauge), so it's
        # queryable as a timeseries in Prometheus/Grafana, not only
        # inspectable as an individual span in the tracing backend.
        get_app_metrics().record_health_summary(summary)

        # ONE span + ONE log line per minute, regardless of how many
        # checks ran (interval_seconds is configurable independently).
        with traced_span(
            "health.summary_1m",
            kind=SpanKind.INTERNAL,
            attributes={
                "app.health.window_seconds": round(summary.window_end - summary.window_start, 1),
                "app.health.checks_total": summary.total,
                "app.health.checks_success": summary.success,
                "app.health.checks_failure": summary.failure,
                "app.health.success_rate": summary.success_rate,
                "app.health.latency_avg_ms": summary.latency_avg_ms,
                "app.health.latency_min_ms": summary.latency_min_ms,
                "app.health.latency_max_ms": summary.latency_max_ms,
                "app.health.latency_p95_ms": summary.latency_p95_ms,
            },
        ):
            logger.info(
                "Health summary (1m) | checks=%s success_rate=%s avg_ms=%s p95_ms=%s",
                summary.total,
                summary.success_rate,
                summary.latency_avg_ms,
                summary.latency_p95_ms,
            )
