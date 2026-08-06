"""
Wires up the OpenTelemetry SDK once at process start.

Design goal (requirement: "make observability framework independent"):
the ONLY thing that changes when you switch from Langfuse to LangSmith
to a self-hosted OTel backend is the value of OBSERVABILITY_PROVIDER
(+ its credentials) in the environment. Every call-site in this codebase
talks to the standard `opentelemetry.trace` API and never imports a
vendor SDK directly (the one exception - LANGFUSE_DIRECT mode - still
only touches this file, nothing downstream).
"""
from __future__ import annotations

import base64
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased, Sampler, TraceIdRatioBased

from app.config import ObservabilityProvider, Settings
from app.observability.redaction import RedactingSpanExporter
from app.observability.sampling import ForceTraceSampler

logger = logging.getLogger(__name__)

_configured = False


def _basic_auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def _build_exporter(settings: Settings) -> tuple[object, str]:
    """Return (SpanExporter, human_readable_description)."""

    provider = settings.observability_provider

    if provider == ObservabilityProvider.COLLECTOR:
        # App is 100% vendor-agnostic here: it just ships OTLP/HTTP to a
        # sidecar collector. The collector config decides the real backend.
        endpoint = f"{settings.otel_exporter_otlp_endpoint.rstrip('/')}/v1/traces"
        if settings.otel_tls_enabled:
            # mTLS to the collector: certificate_file verifies the
            # collector's server cert (against our shared CA);
            # client_certificate_file/client_key_file are this app's own
            # identity, which the collector's receiver is configured to
            # require (see collector/otel-collector-config.tls.yaml).
            # Endpoint must be https:// here - see config.py validation.
            exporter = OTLPSpanExporter(
                endpoint=endpoint,
                certificate_file=settings.otel_tls_ca_file,
                client_certificate_file=settings.otel_tls_client_cert_file,
                client_key_file=settings.otel_tls_client_key_file,
            )
            return exporter, f"OTLP -> collector, mTLS ({endpoint})"
        return OTLPSpanExporter(endpoint=endpoint), f"OTLP -> collector, plaintext ({endpoint})"

    if provider == ObservabilityProvider.LANGFUSE_DIRECT:
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            raise RuntimeError("LANGFUSE_DIRECT provider requires LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY")
        endpoint = f"{settings.langfuse_host.rstrip('/')}/api/public/otel/v1/traces"
        auth_header = _basic_auth_header(settings.langfuse_public_key, settings.langfuse_secret_key)
        headers = {"Authorization": auth_header}
        return OTLPSpanExporter(endpoint=endpoint, headers=headers), f"OTLP -> Langfuse direct ({endpoint})"

    if provider == ObservabilityProvider.LANGSMITH_DIRECT:
        if not settings.langsmith_api_key:
            raise RuntimeError("LANGSMITH_DIRECT provider requires LANGSMITH_API_KEY")
        endpoint = f"{settings.langsmith_otlp_endpoint.rstrip('/')}/v1/traces"
        headers = {
            "x-api-key": settings.langsmith_api_key,
            "Langsmith-Project": settings.langsmith_project,
        }
        return OTLPSpanExporter(endpoint=endpoint, headers=headers), f"OTLP -> LangSmith direct ({endpoint})"

    if provider == ObservabilityProvider.CONSOLE:
        return ConsoleSpanExporter(), "console (stdout)"

    raise ValueError(f"Unknown observability provider: {provider}")


def _build_sampler(settings: Settings) -> Sampler:
    """
    Head-based, trace-consistent sampling.

    `ParentBased(TraceIdRatioBased(ratio))`:
      - The sampling decision is made ONCE, at the root span, by hashing
        the trace id against `ratio`. Every child span inherits that
        decision (`ParentBased`), so you never get a half-exported trace
        (e.g. the root span present but the litellm.completion child
        missing) - a plain per-span probabilistic sampler could do that.
      - At ratio=1.0 we skip the probabilistic sampler entirely and use
        ALWAYS_ON - cheaper (no hashing) and behaviourally identical.
      - The result is always wrapped in `ForceTraceSampler`, so the
        `X-Force-Trace` header (see app/api/routes.py + app/security/auth.py)
        can override this decision for one request, regardless of ratio.

    See README "Sampling" section for the tradeoff vs. the health-check
    aggregation pattern used elsewhere in this service, and "Load-based
    sampling" for why the actual rate limiting under load happens in the
    Collector's tail_sampling processor, not here.
    """
    head_sampling_active = settings.trace_sampling_ratio < 1.0
    if settings.observability_provider == ObservabilityProvider.COLLECTOR and head_sampling_active:
        # The Collector's tail_sampling processor (collector/otel-collector-config.yaml)
        # promises "always keep error traces" - but it can only decide on
        # traces that actually reach it. If the SDK head-samples traces
        # away first, that promise silently stops being true for whatever
        # fraction got dropped here. Not a hard error (you may have a
        # deliberate reason), but too easy a footgun to pass silently.
        logger.warning(
            "TRACE_SAMPLING_RATIO=%s with OBSERVABILITY_PROVIDER=collector: the Collector's "
            "tail_sampling processor can only evaluate traces that reach it. Head-sampling "
            "traces away here means its 'always keep errors' policy won't see them either. "
            "Set TRACE_SAMPLING_RATIO=1.0 and let the Collector's rate_limiting policy do the "
            "load-based sampling instead, unless this is intentional.",
            settings.trace_sampling_ratio,
        )

    ratio = settings.trace_sampling_ratio
    base_sampler = ALWAYS_ON if ratio >= 1.0 else ParentBased(TraceIdRatioBased(ratio))

    # Wrap unconditionally: the X-Force-Trace header (app/api/routes.py)
    # needs to override this sampler's decision regardless of what ratio
    # is configured. See app/observability/sampling.py for why this has
    # to be a wrapper rather than a baggage check inside TraceIdRatioBased.
    return ForceTraceSampler(base_sampler)


def configure_observability(settings: Settings) -> TracerProvider:
    """
    Idempotent. Safe to call once at startup. Returns the configured
    TracerProvider so callers (e.g. FastAPI instrumentation) can use it.
    """
    global _configured

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.app_env,
        }
    )
    tracer_provider = TracerProvider(resource=resource, sampler=_build_sampler(settings))

    exporter, description = _build_exporter(settings)

    # Layer 1 of the PII redaction plan (docs/SECURITY-PLAN.md Section 2.1):
    # wrap whichever exporter was just built so every string span attribute
    # is regex-redacted before it leaves the process. For CONSOLE mode this
    # runs inline (SimpleSpanProcessor, see below) - fine, it's dev-only and
    # the cost is sub-millisecond. For every network exporter it runs on
    # BatchSpanProcessor's background export thread - zero added /chat
    # latency, verified in Section 2.3.
    if settings.pii_redaction_enabled:
        exporter = RedactingSpanExporter(exporter)
        description = f"{description}, PII-redacted (Layer 1)"

    # Console exporter uses Simple processor so output is immediate/ordered
    # in local debugging; every network exporter uses Batch for throughput.
    if settings.observability_provider == ObservabilityProvider.CONSOLE:
        tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_queue_size=2048,
                schedule_delay_millis=2000,
                max_export_batch_size=512,
            )
        )

    trace.set_tracer_provider(tracer_provider)
    _configured = True

    logger.info(
        "Observability configured | provider=%s | export=%s | trace_sampling_ratio=%s",
        settings.observability_provider.value,
        description,
        settings.trace_sampling_ratio,
    )
    return tracer_provider


def get_tracer(instrumentation_name: str = "genai-observability-service"):
    return trace.get_tracer(instrumentation_name)
