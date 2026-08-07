"""Prometheus metrics.

Deliberately a direct `prometheus_client` registry scraped at `/metrics`,
not a second OTLP metrics pipeline - traces go through OTel/OTLP (see
`tracing.py`), metrics are pulled directly by Prometheus. Running both a
push (OTLP) and pull (Prometheus) pipeline for metrics on a single-replica
demo app would be observability infrastructure with no measured need.

Cardinality discipline: every label set below is a small, closed enum
(route *templates*, provider names, status buckets, tool names) - never a
raw city name, coordinate, trace ID, or request ID. See
`tests/unit/test_metrics_cardinality.py`.
"""
from __future__ import annotations

import logging
from wsgiref.simple_server import WSGIServer

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)

logger = logging.getLogger(__name__)

REGISTRY = CollectorRegistry()

http_requests_total = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status_code"], registry=REGISTRY
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request duration", ["method", "route"], registry=REGISTRY
)

ui_operations_total = Counter(
    "ui_operations_total", "UI operations", ["operation", "status"], registry=REGISTRY
)
ui_operation_duration_seconds = Histogram(
    "ui_operation_duration_seconds", "UI operation duration", ["operation"], registry=REGISTRY
)

weather_requests_total = Counter(
    "weather_requests_total", "Weather lookups", ["path_type", "cache_status"], registry=REGISTRY
)
weather_request_duration_seconds = Histogram(
    "weather_request_duration_seconds", "Weather lookup duration", ["path_type"], registry=REGISTRY
)

open_meteo_request_duration_seconds = Histogram(
    "open_meteo_request_duration_seconds", "Open-Meteo upstream call duration", ["provider"], registry=REGISTRY
)
open_meteo_failures_total = Counter(
    "open_meteo_failures_total", "Open-Meteo upstream failures", ["provider", "error_type"], registry=REGISTRY
)

cache_hits_total = Counter("cache_hits_total", "Weather cache hits", registry=REGISTRY)
cache_misses_total = Counter("cache_misses_total", "Weather cache misses", registry=REGISTRY)

active_outbound_requests = Gauge(
    "active_outbound_requests", "In-flight outbound HTTP requests to Open-Meteo", registry=REGISTRY
)

agent_runs_total = Counter("agent_runs_total", "PydanticAI agent runs", ["status"], registry=REGISTRY)
agent_run_duration_seconds = Histogram(
    "agent_run_duration_seconds", "PydanticAI agent run duration", registry=REGISTRY
)

tool_calls_total = Counter(
    "tool_calls_total", "Agent tool invocations", ["tool_name", "status"], registry=REGISTRY
)
tool_call_duration_seconds = Histogram(
    "tool_call_duration_seconds", "Agent tool call duration", ["tool_name"], registry=REGISTRY
)

litellm_request_duration_seconds = Histogram(
    "litellm_request_duration_seconds", "LiteLLM Proxy request duration", registry=REGISTRY
)
llm_tokens_total = Counter("llm_tokens_total", "LLM token usage", ["direction"], registry=REGISTRY)
llm_estimated_cost_usd_total = Counter(
    "llm_estimated_cost_usd_total", "Estimated LLM cost in USD", registry=REGISTRY
)
structured_output_failures_total = Counter(
    "structured_output_failures_total", "Agent structured-output validation failures", registry=REGISTRY
)

batch_runs_total = Counter("batch_runs_total", "Daily collection batch runs", ["status"], registry=REGISTRY)
batch_run_duration_seconds = Histogram(
    "batch_run_duration_seconds", "Daily collection batch run duration", registry=REGISTRY
)
batch_locations_total = Counter(
    "batch_locations_total", "Locations processed by daily collection", ["result"], registry=REGISTRY
)

sqlite_operation_duration_seconds = Histogram(
    "sqlite_operation_duration_seconds", "SQLite operation duration", ["operation"], registry=REGISTRY
)
sqlite_busy_errors_total = Counter(
    "sqlite_busy_errors_total", "SQLite busy/locked errors", registry=REGISTRY
)

scheduler_misfires_total = Counter(
    "scheduler_misfires_total", "APScheduler job misfires", registry=REGISTRY
)

rate_limit_rejections_total = Counter(
    "rate_limit_rejections_total", "Requests rejected by the IP rate limiter", registry=REGISTRY
)

auth_requests_total = Counter(
    "auth_requests_total", "Authentication attempts", ["operation", "status"], registry=REGISTRY
)


def render_latest() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def start_metrics_server(port: int, addr: str = "0.0.0.0") -> WSGIServer:
    """Starts prometheus_client's own lightweight WSGI server on its own
    port/thread, serving THIS module's registry - deliberately not a
    FastAPI route, so it can be firewalled independently of the main app
    port (see settings.py's `metrics_port` docstring)."""
    server, _thread = start_http_server(port, addr=addr, registry=REGISTRY)
    logger.info("metrics server listening on %s:%d", addr, port)
    return server


def stop_metrics_server(server: WSGIServer) -> None:
    server.shutdown()
    server.server_close()
    logger.info("metrics server stopped")
