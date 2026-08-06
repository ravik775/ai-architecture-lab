from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from opentelemetry import context as context_api
from opentelemetry.trace import SpanKind
from pydantic import BaseModel, Field, field_validator

from app.config import get_settings
from app.llm.memory import store
from app.observability.metrics import get_app_metrics
from app.observability.sampling import with_baggage_context
from app.observability.tracing import current_trace_id, traced_span
from app.security.auth import PERMISSION_FORCE_TRACE, Principal, authenticate
from app.security.rate_limit import get_rate_limiter

logger = logging.getLogger("app.api")
router = APIRouter()

FORCE_TRACE_HEADER_NAME = "X-Force-Trace"


# ---------------------------------------------------------------- chat --
class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        # min_length=1 alone lets " " (a single space) through - this is
        # the basic input guardrail: reject whitespace-only messages
        # outright rather than spending an LLM call on nothing. Content
        # itself is intentionally NOT validated beyond this (no keyword
        # denylist) - that class of check is fragile/easily bypassed and
        # documented as a real gap in the risk register, not solved here.
        if not value.strip():
            raise ValueError("message must not be blank or whitespace-only")
        return value


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    finish_reason: str
    latency_ms: float
    trace_id: str | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    principal: Principal = Depends(authenticate),
) -> ChatResponse:
    runner = request.app.state.chat_runner
    if runner is None:
        raise HTTPException(status_code=503, detail="LLM runner not initialized")

    # Rate-limit guardrail (OWASP LLM10, Unbounded Consumption) - separate
    # budget from the Collector's tail_sampling rate limiter, which
    # protects the observability pipeline, not OpenRouter spend. Keyed by
    # the authenticated principal, so each API key gets its own bucket;
    # if auth is disabled (no API_KEYS configured), every anonymous caller
    # shares one bucket under the "anonymous" key_id - the best available
    # granularity when callers can't be told apart at all.
    limiter = get_rate_limiter(get_settings().rate_limit_requests_per_minute)
    if limiter is not None:
        limiter.check(principal.key_id)

    # X-Force-Trace: honored only if this caller's API key carries the
    # force_trace permission; otherwise the header is silently ignored -
    # not a 403. Sending a header you're not allowed to use isn't itself
    # an error, it just doesn't do anything (see app/security/auth.py and
    # docs/SECURITY-PLAN.md Section 6.3 for why: forcing full tracing is
    # also forcing extra load per request, so it's gated, but a stray
    # header shouldn't break a caller's request).
    force_trace_requested = request.headers.get(FORCE_TRACE_HEADER_NAME, "").strip().lower() == "true"
    force_trace_granted = force_trace_requested and principal.has(PERMISSION_FORCE_TRACE)
    if force_trace_requested and not force_trace_granted:
        logger.info(
            "X-Force-Trace requested but ignored - key %s lacks force_trace permission",
            principal.key_id,
        )

    ctx = with_baggage_context(force=force_trace_granted)
    token = context_api.attach(ctx)
    try:
        # Root span for the whole request. Everything the graph/litellm do
        # below nests under this via OTel's implicit context propagation.
        # Runs inside the attached context above, so ForceTraceSampler
        # (app/observability/sampling.py) sees the baggage set on it, if any.
        with traced_span(
            "chat.request",
            kind=SpanKind.SERVER,
            attributes={
                "app.session_id": payload.session_id,
                "app.endpoint": "/chat",
                "app.request.message_length": len(payload.message),
                "app.auth.key_id": principal.key_id,
                "app.trace.forced": force_trace_granted,
            },
        ) as span:
            try:
                result = runner.run(payload.session_id, payload.message)
            except Exception as exc:  # noqa: BLE001
                logger.exception("chat graph failed")
                get_app_metrics().record_chat_request("error")
                raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc

            get_app_metrics().record_chat_request("success")

            trace_id = current_trace_id()
            span.set_attribute("app.response.trace_id", trace_id or "unknown")

            return ChatResponse(
                session_id=payload.session_id,
                reply=result.get("assistant_message", ""),
                model=result.get("model", ""),
                prompt_tokens=result.get("prompt_tokens", 0),
                completion_tokens=result.get("completion_tokens", 0),
                total_tokens=result.get("total_tokens", 0),
                cost_usd=result.get("cost_usd", 0.0),
                finish_reason=result.get("finish_reason", "unknown"),
                latency_ms=result.get("latency_ms", 0.0),
                trace_id=trace_id,
            )
    finally:
        context_api.detach(token)


@router.get("/chat/{session_id}/history")
async def chat_history(session_id: str, principal: Principal = Depends(authenticate)) -> dict:
    return {"session_id": session_id, "history": store.get_history(session_id)}


@router.delete("/chat/{session_id}")
async def clear_chat(session_id: str, principal: Principal = Depends(authenticate)) -> dict:
    store.clear(session_id)
    return {"session_id": session_id, "cleared": True}


# -------------------------------------------------------------- health --
@router.get("/health/live")
async def health_live(request: Request) -> dict:
    """
    Cheap liveness probe - intended to be polled every ~2s by an
    orchestrator (docker/k8s). Returns the most recent internal probe
    result without doing any new work.
    """
    monitor = request.app.state.health_monitor
    last = monitor.last_check
    if last is None:
        return {"status": "starting"}
    return {
        "status": "ok" if last.ok else "degraded",
        "components": last.components,
        "checked_at": last.timestamp,
        "latency_ms": last.latency_ms,
    }


@router.get("/health/summary")
async def health_summary(request: Request) -> dict:
    """
    Aggregated 1-minute window (sampling summary) - this is what actually
    gets exported to the observability backend, so this endpoint is the
    human-facing mirror of what you'll see in Langfuse/LangSmith/collector.
    """
    monitor = request.app.state.health_monitor
    summary = monitor.last_summary
    if summary is None:
        return {"status": "no summary yet", "buffered_checks": monitor.buffered_count}
    return {
        "window_start": summary.window_start,
        "window_end": summary.window_end,
        "checks_total": summary.total,
        "checks_success": summary.success,
        "checks_failure": summary.failure,
        "success_rate": summary.success_rate,
        "latency_avg_ms": summary.latency_avg_ms,
        "latency_min_ms": summary.latency_min_ms,
        "latency_max_ms": summary.latency_max_ms,
        "latency_p95_ms": summary.latency_p95_ms,
        "buffered_checks_since_window": monitor.buffered_count,
    }
