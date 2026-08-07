"""Structured JSON logging setup.

Every log line carries trace_id/span_id (from the active OTel span) and
request_id/correlation_id/job_id (from `context.py`'s contextvars) - see
`TraceContextFilter` below, wired in `configure_logging`.
"""
from __future__ import annotations

import logging
import sys

from pythonjsonlogger import jsonlogger

_CONFIGURED = False


class TraceContextFilter(logging.Filter):
    """Injects trace_id/span_id (hex, zero-padded) into every log record.

    Uses the OTel API only (not the SDK) so this filter works whether or
    not tracing is enabled/sampled - unsampled/absent spans yield "0"s
    rather than raising.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx.is_valid:
                record.trace_id = format(ctx.trace_id, "032x")
                record.span_id = format(ctx.span_id, "016x")
            else:
                record.trace_id = "0" * 32
                record.span_id = "0" * 16
        except Exception:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16

        try:
            from app.observability.context import correlation_id_var, job_id_var, request_id_var

            record.request_id = request_id_var.get()
            record.correlation_id = correlation_id_var.get()
            record.job_id = job_id_var.get()
        except Exception:
            pass
        return True


def configure_logging(*, level: str = "INFO", service_name: str = "weather-intelligence-agent") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt=(
            "%(asctime)s %(levelname)s %(name)s %(message)s %(trace_id)s %(span_id)s "
            "%(request_id)s %(correlation_id)s %(job_id)s"
        ),
        rename_fields={"asctime": "timestamp", "levelname": "level"},
        defaults={"service": service_name, "request_id": "", "correlation_id": "", "job_id": ""},
    )
    handler.setFormatter(formatter)
    handler.addFilter(TraceContextFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Quiet noisy third-party loggers at INFO+ unless explicitly raised.
    for noisy in ("httpx", "httpcore", "apscheduler", "nicegui", "socketio", "engineio"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))

    _CONFIGURED = True
