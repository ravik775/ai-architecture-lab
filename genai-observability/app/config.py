"""
Central configuration for the service.

All observability provider switching happens through env vars only -
no code changes are required to move between Langfuse, LangSmith, a
generic OTel backend (Jaeger/Grafana Tempo/etc.), or plain console
output. See README.md "Switching providers" section.
"""
from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilityProvider(str, Enum):  # noqa: UP042 - see note below
    """
    How spans leave this process.

    COLLECTOR (recommended / default):
        The app only knows about the OpenTelemetry SDK. It exports OTLP/HTTP
        to a local OpenTelemetry Collector sidecar (see collector/otel-collector-config.yaml).
        The Collector, NOT the app, decides which backend(s) receive the data
        (Langfuse, LangSmith, Jaeger, console, or several at once via fan-out).
        Switching backends = editing the collector config / env vars, zero app changes.

    LANGFUSE_DIRECT:
        Skip the collector and export OTLP straight to Langfuse's native OTLP
        endpoint. Useful for local dev or when you don't want to run a collector.

    LANGSMITH_DIRECT:
        Skip the collector and export OTLP straight to LangSmith's OTLP endpoint.

    CONSOLE:
        Pretty-print spans to stdout. Useful for local debugging / CI, no network calls.

    Deliberately `(str, Enum)`, not `enum.StrEnum`: the Dockerfile pins
    python:3.11-slim, but `StrEnum` only exists from 3.11 onward - this
    codebase's dev/test tooling (this sandbox included, and possibly
    contributors' local machines) may run 3.10, where `StrEnum` doesn't
    exist at all. `(str, Enum)` works identically for this codebase's
    actual usage (`.value` everywhere) back to 3.7+, so there's no reason
    to narrow compatibility for a purely cosmetic modernization.
    """

    COLLECTOR = "collector"
    LANGFUSE_DIRECT = "langfuse_direct"
    LANGSMITH_DIRECT = "langsmith_direct"
    CONSOLE = "console"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Service identity ---
    service_name: str = Field(default="genai-observability-service")
    service_version: str = Field(default="1.0.0")
    app_env: str = Field(default="dev")

    # --- Observability provider switch (framework independence) ---
    observability_provider: ObservabilityProvider = Field(default=ObservabilityProvider.COLLECTOR)

    # OTLP endpoint of the local collector (used when provider == COLLECTOR)
    otel_exporter_otlp_endpoint: str = Field(default="http://otel-collector:4318")

    # mTLS to the collector - opt-in, off by default (docker-compose.tls.yml
    # flips this on and mounts the certs from certs/generate-certs.sh).
    # When enabled, otel_exporter_otlp_endpoint should use https://.
    otel_tls_enabled: bool = Field(default=False)
    otel_tls_ca_file: str = Field(default="/certs/ca.crt")
    otel_tls_client_cert_file: str = Field(default="/certs/app.crt")
    otel_tls_client_key_file: str = Field(default="/certs/app.key")

    # Fraction of traces to keep, decided once per trace (ParentBased/TraceIdRatioBased).
    # 1.0 = trace everything (default, fine for dev/low traffic).
    # e.g. 0.2 = keep 20% of traces, drop the rest before they're even
    # exported - use once volume makes 100% tracing expensive. See
    # README "Sampling" for the tradeoff vs. the health-check aggregation
    # pattern used elsewhere in this service.
    trace_sampling_ratio: float = Field(default=1.0, ge=0.0, le=1.0)

    # How often the OTel MetricReader flushes aggregated metrics (request
    # rate, token cost, etc.) to the configured exporter.
    metrics_export_interval_seconds: float = Field(default=15.0)

    # Langfuse (used by collector config AND by LANGFUSE_DIRECT mode)
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    # LangSmith (used by collector config AND by LANGSMITH_DIRECT mode)
    langsmith_api_key: str = Field(default="")
    langsmith_otlp_endpoint: str = Field(default="https://api.smith.langchain.com/otel")
    langsmith_project: str = Field(default="genai-observability-service")

    # --- LLM / OpenRouter (via litellm) ---
    openrouter_api_key: str = Field(default="")
    openrouter_model: str = Field(default="openrouter/meta-llama/llama-3.1-8b-instruct")
    llm_temperature: float = Field(default=0.3)
    llm_max_tokens: int = Field(default=512)
    llm_request_timeout_seconds: float = Field(default=30.0)

    # --- Health monitor sampling ---
    health_check_interval_seconds: float = Field(default=2.0)
    health_summary_window_seconds: float = Field(default=60.0)

    # --- API-key auth + RBAC for the /chat integration point ---
    # Format: "key1:perm1,perm2;key2:perm1" - semicolon-separated keys,
    # each with a comma-separated permission list. Recognized permissions:
    #   "chat"        - required to call POST/GET/DELETE /chat*
    #   "force_trace" - required for the X-Force-Trace header to be honored
    # Empty (default) = auth is effectively disabled; see app/security/auth.py
    # for what that means and why it's not the deployable default.
    api_keys: str = Field(default="")

    # --- Rate limiting guardrail on /chat (OWASP LLM10, Unbounded Consumption) ---
    # Per-API-key token bucket (app/security/rate_limit.py) - independent of
    # the Collector-side tail_sampling rate limiter, which protects the
    # observability pipeline, not OpenRouter spend. <= 0 disables it.
    rate_limit_requests_per_minute: float = Field(default=30.0)

    # --- PII redaction (Layers 1/2/4 - docs/SECURITY-PLAN.md Section 2) ---
    # Gates Layer 1 (RedactingSpanExporter, app/observability/redaction.py)
    # and Layer 4 (PIIRedactionLogFilter). Layer 2 (Collector `redaction`
    # processor) is collector-side config, not app config, so it's NOT
    # controlled by this flag - it stays active regardless, which is the
    # point of defense in depth: Layer 2 doesn't depend on this app doing
    # the right thing. Default True; only turn off for local debugging
    # where you deliberately want to see raw span/log content.
    pii_redaction_enabled: bool = Field(default=True)

    # --- HTTP server ---
    # 0.0.0.0 is intentional, not an oversight (a security linter will
    # flag this as "binds all interfaces"): this process runs inside a
    # Docker container (see Dockerfile/docker-compose.yml) and MUST
    # accept connections from outside its own network namespace to be
    # reachable at all - binding to 127.0.0.1 here would make the
    # service unreachable even from other containers on the same
    # Docker network, let alone the host's published port mapping.
    host: str = Field(default="0.0.0.0")  # noqa: S104
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    return Settings()
