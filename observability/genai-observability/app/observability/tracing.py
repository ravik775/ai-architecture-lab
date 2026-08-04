"""
Thin helpers on top of the standard OpenTelemetry API for building a
*hierarchy* of spans with consistent, GenAI-flavoured attributes.

Why not a custom abstraction class wrapping OTel? Because OTel's
context propagation IS the vendor-neutral hierarchy mechanism already -
wrapping it would just be re-inventing it with extra steps. Every span
opened with `traced_span(...)` below automatically nests under whatever
span is currently active (root request span -> graph span -> node span
-> llm-call span), and that parent/child tree is exactly what Langfuse
renders as trace -> observations, and what LangSmith renders as a run tree.

Attribute naming follows the OpenTelemetry Semantic Conventions for
Generative AI (`gen_ai.*`) where an equivalent exists, and falls back to
an `app.*` namespace for anything domain-specific. NOTE (honesty check,
verified against docs as of Aug 2026): Langfuse's OTel ingestion maps
`gen_ai.*` attributes natively. LangSmith's OTel endpoint currently
expects the OpenLLMetry convention primarily and is still rolling out
`gen_ai.*` support - if you run in LANGSMITH_DIRECT mode and traces look
sparse in the UI, that's the likely reason; the collector fan-out path
lets you attach a translation processor without touching app code.
"""
from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from app.observability.redaction import redact
from app.observability.setup import get_tracer

_tracer = get_tracer()


@contextmanager
def traced_span(
    name: str,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[Span]:
    """
    Open a span that nests under the current active span (if any).
    Records duration, exceptions, and status automatically.
    """
    start = time.perf_counter()
    with _tracer.start_as_current_span(name, kind=kind) as span:
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:  # noqa: BLE001 - re-raised after recording
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            span.set_attribute("app.duration_ms", round((time.perf_counter() - start) * 1000, 2))


def set_llm_request_attributes(
    span: Span,
    *,
    system: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> None:
    span.set_attribute("gen_ai.system", system)
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("gen_ai.request.temperature", temperature)
    span.set_attribute("gen_ai.request.max_tokens", max_tokens)


def set_llm_response_attributes(
    span: Span,
    *,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    finish_reason: str | None = None,
    cost_usd: float | None = None,
    latency_ms: float | None = None,
) -> None:
    if model:
        span.set_attribute("gen_ai.response.model", model)
    if prompt_tokens is not None:
        span.set_attribute("gen_ai.usage.prompt_tokens", prompt_tokens)
    if completion_tokens is not None:
        span.set_attribute("gen_ai.usage.completion_tokens", completion_tokens)
    if total_tokens is not None:
        span.set_attribute("gen_ai.usage.total_tokens", total_tokens)
    if finish_reason:
        span.set_attribute("gen_ai.response.finish_reasons", [finish_reason])
    if cost_usd is not None:
        span.set_attribute("app.llm.cost_usd", cost_usd)
    if latency_ms is not None:
        span.set_attribute("app.llm.latency_ms", latency_ms)


def set_llm_content_attributes(
    span: Span,
    *,
    prompt: str | None = None,
    completion: str | None = None,
) -> None:
    """
    NOT called anywhere in this codebase today - content isn't captured on
    spans by default (see this module's docstring and the current-state
    audit in `docs/SECURITY-PLAN.md` Section 1: `chat.request` records
    `app.request.message_length`, an int, never the message itself).

    This exists so that if a future need for prompt/completion visibility
    comes up, redaction is already wired in and tested
    (`tests/test_redaction.py`) rather than retrofitted under time
    pressure - this is the one and only place LLM content should ever be
    attached to a span, and it always redacts first.

    Note: `RedactingSpanExporter` (Layer 1) would also catch anything set
    here on its own, since it redacts every string attribute on every
    span regardless of key - the explicit `redact()` calls below are
    belt-and-suspenders, not the only thing standing between this and a
    leak.

    If you do start calling this: the Collector's `redaction` processor
    (`collector/otel-collector-config.yaml`, Layer 2) runs in allowlist
    mode and does **not** currently allow `gen_ai.prompt`/`gen_ai.completion`
    through - add them to `allowed_keys` there too, deliberately, so
    turning this on is a two-file decision, not a silent gap in the
    defense-in-depth story.
    """
    if prompt is not None:
        span.set_attribute("gen_ai.prompt", redact(prompt))
    if completion is not None:
        span.set_attribute("gen_ai.completion", redact(completion))


def current_trace_id() -> str | None:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx or ctx.trace_id == 0:
        return None
    return format(ctx.trace_id, "032x")
