# GenAI Observability Reference Service

A minimal, Docker-composable FastAPI service that demonstrates a
production-shaped observability stack for LLM applications: hierarchical
tracing with head-based sampling, a vendor-agnostic export path, a
metrics pipeline (request rate, token cost/minute), sampled health
checks, and a litellm -> OpenRouter -> LangGraph chat pipeline as the
thing being observed.

The LLM use case is intentionally simple (stateless in-memory chat). The
point of this repo is the observability plumbing around it, not the
chat feature itself.

## Architecture

```
                 ┌─────────────────────────────────────────┐
                 │              FastAPI app                 │
                 │                                           │
 POST /chat ───► │  chat.request (root span, sampled)         │
                 │    └─ graph.execute (LangGraph)            │
                 │         ├─ node.load_memory                │
                 │         ├─ node.llm_generate                │
                 │         │    └─ litellm.completion           │
                 │         │         (OpenRouter, gen_ai.* attrs)│
                 │         └─ node.persist_memory               │
                 │                                           │
                 │  HealthMonitor (background task)          │
                 │    every 2s  -> probe, buffer in memory    │
                 │    every 60s -> health.summary_1m span      │
                 │                  + health metrics           │
                 │                                           │
                 │  Metrics: request rate, token cost/min,    │
                 │  LLM call duration/tokens, health success  │
                 │  rate (opentelemetry.metrics, independent   │
                 │  MetricReader pipeline)                     │
                 └────────┬──────────────────────┬─────────────┘
                          │ OTLP/HTTP (spans,      │ OTLP/HTTP (metrics)
                          │ sampled by ratio)      │
                          ▼                        ▼
                      ┌───────────────────────────────────┐
                      │       OpenTelemetry Collector       │
                      │      (collector/*.yaml config)      │
                      └──┬──────────┬───────────────┬───────┘
                         │          │               │
                 Langfuse│  LangSmith│      Prometheus exporter
                 OTLP    │  OTLP     │      (:8889, scraped by the
                         ▼          ▼      `prometheus` service)
              cloud.langfuse.com  api.smith.langchain.com   Prometheus :9090
```

Everything above the Collector only ever talks the standard
`opentelemetry` API. Nothing in `app/` imports a Langfuse or LangSmith
SDK for the default path - that's what makes the observability layer
framework-independent (requirement #2). Traces and metrics are two
separate OTel pipelines with separate destinations, because Langfuse and
LangSmith don't ingest OTLP metrics - see "Metrics pipeline" below.

## Span hierarchy & attributes

Every `/chat` call produces one trace with this span tree:

| Span | Notes |
|---|---|
| `chat.request` | root, `SpanKind.SERVER`, `app.session_id`, `app.endpoint` |
| `graph.execute` | wraps the whole LangGraph invocation |
| `node.load_memory` | `app.memory.turns_loaded` |
| `node.llm_generate` | wraps the litellm call |
| `litellm.completion` | `SpanKind.CLIENT`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.*`, `app.llm.cost_usd`, `app.llm.latency_ms` |
| `node.persist_memory` | `app.memory.turns_after` |

Attributes follow the [OpenTelemetry Semantic Conventions for Generative
AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/) (`gen_ai.*`)
where a convention exists, and an `app.*` namespace for everything
domain-specific (session ids, cost, health stats).

## Quick start

```bash
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY and LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY

docker compose up --build
```

Then:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-key-change-me" \
  -d '{"session_id": "demo-1", "message": "Explain OpenTelemetry in one sentence."}'

# Force this one request to full trace fidelity regardless of sampling/rate limiting:
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-key-change-me" \
  -H "X-Force-Trace: true" \
  -d '{"session_id": "demo-1", "message": "Reproduce that bug."}'

curl http://localhost:8000/health/live      # last 2s probe, no auth required
curl http://localhost:8000/health/summary   # last 1-minute aggregate
```

`demo-key-change-me` is the default in `.env.example` (permissions:
`chat`, `force_trace`) so the walkthrough above works unmodified - see
"Access control" below before using this anywhere but localhost.

Traces will appear in your Langfuse project within a few seconds
(the collector batches every 2s). API docs: `http://localhost:8000/docs`.
Metrics land in the bundled Prometheus at `http://localhost:9090` - the
Collector's Prometheus exporter renames dots to underscores and appends
unit/`_total` suffixes, so check the exact exported name first (either
`curl http://localhost:8889/metrics | grep app_llm_cost` or Prometheus's
own metric browser at `/graph`) before writing a query - it will be a
variant of `app_llm_cost_usd_total_*`.

## Switching providers (requirement #2)

Three independent ways to change where traces go, in increasing order
of how much you touch:

1. **Collector config only (recommended)** - keep `OBSERVABILITY_PROVIDER=collector`
   in `.env` (the default). Edit `collector/otel-collector-config.yaml`,
   specifically `service.pipelines.traces.exporters`, to point at
   Langfuse, LangSmith, both, or add e.g. Jaeger/Tempo. Restart only the
   `otel-collector` container - the Python app is untouched.
2. **Direct-export env var, no collector** - set
   `OBSERVABILITY_PROVIDER=langfuse_direct` or `langsmith_direct` in
   `.env` and skip the collector hop entirely. Useful for local dev or
   when you can't run a sidecar.
3. **Console mode** - `OBSERVABILITY_PROVIDER=console` prints spans to
   stdout, no network calls, useful for CI or offline debugging.

All three are implemented in `app/observability/setup.py` in ~15 lines
each; application code (`app/llm/chain.py`, `app/api/routes.py`,
`app/health/monitor.py`) never changes.

### Verified endpoint details (checked against provider docs, Aug 2026)

- **Langfuse**: OTLP/HTTP only (no gRPC yet), `POST {LANGFUSE_HOST}/api/public/otel/v1/traces`,
  Basic Auth with `public_key:secret_key`. Maps `gen_ai.*` attributes natively.
- **LangSmith**: `POST https://api.smith.langchain.com/otel/v1/traces`,
  header `x-api-key: <LANGSMITH_API_KEY>`. LangSmith's OTel ingestion is
  built primarily around the OpenLLMetry semantic convention; native
  `gen_ai.*` support is still rolling out as of this writing, so traces
  routed there may show fewer inferred fields (model/cost/token badges)
  than Langfuse until that lands. If you need full parity today, add a
  collector `transform` processor to remap `gen_ai.*` -> the OpenLLMetry
  attribute names before the `otlphttp/langsmith` exporter.

## Metrics pipeline

Traces answer "what happened in this one request/session" - great for
debugging a specific user's chat, which is what Langfuse/LangSmith are
built for. They're a poor fit for "what's the request rate and token
spend across the whole fleet right now" - that's a timeseries question,
and querying it by scanning spans works at small scale and falls over at
real production volume. So this service runs a second, independent OTel
pipeline for that: a `MeterProvider` + `PeriodicExportingMetricReader`
(`app/observability/metrics.py`), alongside the `TracerProvider`, not
instead of it.

Instruments emitted:

| Instrument | Type | Notes |
|---|---|---|
| `app.chat.requests_total` | Counter | `/chat` requests by `app.status` (success/error) - this is your request rate |
| `gen_ai.client.operation.duration` | Histogram (s) | litellm call duration, by model |
| `gen_ai.client.token.usage` | Histogram (tokens) | prompt/completion tokens, by model + `gen_ai.token.type` |
| `app.llm.cost_usd_total` | Counter (USD) | cumulative OpenRouter spend - `rate(...)` over it in Prometheus gives $/minute |
| `app.health.checks_total` | Counter | mirrors the health monitor's 1-minute summary, by outcome |
| `app.health.success_rate` | Observable gauge | most recent 1-minute health success rate |

The first two rows and `app.llm.cost_usd_total` are the concrete
"request rate" and "token cost per minute" asked for; the health
instruments are a bonus so the health-check summary is queryable as a
timeseries, not only inspectable as an individual span.

**Where metrics go**: `OBSERVABILITY_PROVIDER=collector` (default) routes
metrics OTLP -> collector -> a bundled `prometheus` exporter on
`:8889`, scraped by the `prometheus` service at `http://localhost:9090`
(`collector/prometheus.yml`). This is deliberate and worth understanding
rather than assuming: **neither Langfuse nor LangSmith ingest OTLP
metrics as of this writing** - both are trace/observation stores for LLM
apps, not timeseries databases - so `langfuse_direct` and
`langsmith_direct` modes fall back to `ConsoleMetricExporter` (metrics
print to stdout, nothing is persisted). If you need queryable metrics,
run in collector mode; the traces pipeline can still go to
Langfuse/LangSmith independently in that same mode. Export cadence is
`METRICS_EXPORT_INTERVAL_SECONDS` (default 15s).

## Trace sampling

`TRACE_SAMPLING_RATIO` (default `1.0`, keep everything) controls a
`ParentBased(TraceIdRatioBased(ratio))` sampler configured once in
`app/observability/setup.py::_build_sampler`. Two things worth
understanding about the choice, not just the config knob:

- **Head-based, decided once per trace.** The sampling decision hashes
  the trace id against `ratio` at the *root* span (`chat.request`) and
  every descendant span inherits it via `ParentBased`. That's why it's
  `ParentBased(TraceIdRatioBased(...))` and not a bare
  `TraceIdRatioBased(...)` on every span independently - the latter
  could sample `chat.request` in but drop `litellm.completion`,
  producing a broken partial trace. `ParentBased` guarantees you get a
  trace, complete, or nothing.
- **It's blind to content.** At `ratio=0.2`, an unlucky trace_id hash
  drops a request that happened to error out just as readily as a
  boring successful one. Vanilla `TraceIdRatioBased` sampling cannot
  preserve "always keep errors" - the SDK decides before the request
  even runs, so it has no idea yet whether this call will fail.

`TRACE_SAMPLING_RATIO` stays at its default of `1.0` for a specific
reason now, not just simplicity: **load-based rate limiting has moved to
the Collector** (below), and that only works if the SDK ships every
trace for the Collector to evaluate. `configure_observability()` logs a
warning if you set the ratio below 1.0 while `OBSERVABILITY_PROVIDER=collector`,
because it silently breaks the Collector's "always keep errors"
guarantee for whatever fraction got head-sampled away before arriving.

## Load-based sampling (Collector-side rate limiting)

Rate limiting under load happens in the Collector's `tail_sampling`
processor (`collector/otel-collector-config.yaml`), not in the app.
Two policies, evaluated per trace and OR'd together - a trace is kept if
**either** matches:

```yaml
tail_sampling:
  decision_wait: 5s
  policies:
    - name: always-keep-errors
      type: status_code
      status_code: { status_codes: [ERROR] }
    - name: rate-limit-the-rest
      type: rate_limiting
      rate_limiting: { spans_per_second: 100 }
```

Why Collector-side instead of an SDK-side rate-limiting sampler (the
other valid approach, not used here):

- **Centralized.** One `spans_per_second` budget across every app
  replica, versus one independent token bucket per pod if it lived in
  the SDK.
- **Content-aware.** The Collector sees the whole trace, including
  whether it errored, before deciding - the SDK has to decide at trace
  start, before it knows the outcome. That's what makes "always keep
  errors, rate-limit everything else" a single policy chain here instead
  of two disconnected mechanisms.
- **Off the request path, guaranteed.** `BatchSpanProcessor`
  (`app/observability/setup.py`) already exports spans on a background
  thread - by the time this policy chain runs, the app has long since
  returned its HTTP response to the caller. Tail sampling adds
  Collector-side memory (`num_traces: 50000` buffer cap) and CPU, never
  `/chat` latency, regardless of how much traffic spikes.

## Force-sampling a specific request (`X-Force-Trace`)

Send `X-Force-Trace: true` on a `/chat` call to guarantee that one
request is captured at full fidelity, bypassing both the ratio sampler
and the Collector's rate limit above - useful for "reproduce this bug
right now and make sure I can see it in Langfuse," where waiting on a
probabilistic sampler isn't good enough.

Mechanism (`app/observability/sampling.py`): a `ForceTraceSampler`
wraps the configured sampler and checks OpenTelemetry `Baggage` first,
unconditionally, before ever consulting the ratio/tail-sampling logic.
`app/api/routes.py` sets that baggage key on the request context before
opening the root span, but **only if the caller's API key has the
`force_trace` permission** (RBAC, below) - otherwise the header is
silently ignored (not rejected) and the request proceeds normally. That
gate exists because forcing full tracing is also forcing extra
Collector/backend load per request - see "Access control" below for why
that's not something every caller gets by default.

One boundary worth being explicit about: this header only ever answers
"is this span recorded," never "what's in it" - it does not, and will
never, bypass PII redaction (Layers 1/2/4 in the risk register below).
Forcing a trace and scrubbing what's in it are independent switches by
design.

## Access control (API-key auth + RBAC)

`POST /chat`, `GET /chat/{id}/history`, and `DELETE /chat/{id}` require
an `X-API-Key` header, checked against `API_KEYS`
(`app/security/auth.py`) - format `key1:chat,force_trace;key2:chat`,
semicolon-separated keys each with a comma-separated permission list.
Two permissions exist:

| Permission | Required for |
|---|---|
| `chat` | Any `/chat*` call at all |
| `force_trace` | The `X-Force-Trace` header to actually do anything |

Deliberately minimal - no database, no rotation, no expiry, in-memory
key comparison via `secrets.compare_digest` (constant-time, so a wrong
guess can't be distinguished from a near-miss by timing). This is Phase
1 of `docs/SECURITY-PLAN.md`, scoped narrower than a real deployment
needs on purpose; see the risk register below for what's explicitly not
covered by this (key rotation, hashed storage, expiry).

**Fail-open by design, loud about it.** If `API_KEYS` is left empty,
auth is disabled entirely and every caller gets an anonymous principal
with the `chat` permission (never `force_trace` - that stays opt-in-only
via an explicit key, even with auth off). `.env.example` ships a working
demo key (`demo-key-change-me:chat,force_trace`) rather than leaving
this blank, specifically so the default `docker compose up` experience
still works out of the box - but the name is the reminder: rotate it
before this leaves your machine. `main.py`'s startup log states which
mode you're in, every time, so this is never a silent default:

```
API-key auth is ENABLED on /chat* (API_KEYS configured).
# or:
API_KEYS is not set - /chat* is running WITHOUT authentication. ...
```

`/health/*` endpoints stay open regardless - no cost or user data behind
them, and gating an orchestrator's liveness probe behind a credential is
its own operational hazard.

### Creating an API key

There's no key-management endpoint or database - a key is just a random
string you generate yourself and add to `API_KEYS`. Three steps:

**1. Generate a random key.** Anything unguessable works; this is a
convenient one-liner:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# e.g. 8fJ3k9QpN...  (32 bytes, URL-safe base64)
```

**2. Add it to `API_KEYS` in `.env`**, deciding which permissions it
gets (`chat`, optionally `force_trace`). Multiple keys are
semicolon-separated:

```bash
# One key, chat only:
API_KEYS=8fJ3k9QpN...:chat

# Two keys - an ops/debugging key with force_trace, a regular caller without:
API_KEYS=8fJ3k9QpN...:chat,force_trace;aZ1mR7wLx...:chat
```

**3. Restart the app** (`docker compose restart app` or re-run
`docker compose up`) so it picks up the new `API_KEYS` value - it's read
once at startup via the cached `get_settings()`, not hot-reloaded.

Then use it:

```bash
# Basic chat call
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 8fJ3k9QpN..." \
  -d '{"session_id": "demo", "message": "Hello!"}'

# A key without force_trace can still send the header - it's just ignored
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: aZ1mR7wLx..." \
  -H "X-Force-Trace: true" \
  -d '{"session_id": "demo", "message": "This request is NOT force-traced"}'

# A key with force_trace actually forces sampling
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 8fJ3k9QpN..." \
  -H "X-Force-Trace: true" \
  -d '{"session_id": "demo", "message": "This request IS force-traced"}'

# No key / wrong key -> 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo", "message": "hi"}'
# 401

# Past the per-key rate limit -> 429 with Retry-After
# (send more than RATE_LIMIT_REQUESTS_PER_MINUTE requests inside a minute)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: 8fJ3k9QpN..." \
  -d '{"session_id": "demo", "message": "hi"}'
# 429 (once the bucket for this key is exhausted)
```

Revoking a key is the same idea in reverse: delete its entry from
`API_KEYS` and restart. There's no expiry or rotation schedule - that's
Phase 3 scope (secrets-manager-backed keys), explicitly deferred; see
the risk register below.

## Transport security (TLS / mTLS)

Opt-in overlay, off by default so the plain `docker compose up` path
stays zero-config:

```bash
./certs/generate-certs.sh
docker compose -f docker-compose.yml -f docker-compose.tls.yml up --build
```

What that turns on, and nothing else:

- **App -> Collector**: mutual TLS. The app presents a client
  certificate (`certs/app.crt`/`.key`); the Collector's OTLP/HTTP
  receiver has `client_ca_file` set (`collector/otel-collector-config.tls.yaml`),
  which requires and verifies it. Both trace and metric OTLP exporters
  (`app/observability/setup.py`, `app/observability/metrics.py`) take
  the same three settings: `OTEL_TLS_CA_FILE` (verify the Collector's
  server cert), `OTEL_TLS_CLIENT_CERT_FILE`/`OTEL_TLS_CLIENT_KEY_FILE`
  (this app's own identity).
- **Collector -> Prometheus (scrape)**: the Collector's `prometheus`
  exporter serves `:8889` over TLS; `collector/prometheus.tls.yml` adds
  `scheme: https` + `tls_config.ca_file` so Prometheus verifies it.
- **Collector -> Langfuse/LangSmith egress**: already TLS - both are
  `https://` cloud endpoints regardless of this overlay. Nothing to add
  here; noted so the "what does TLS actually cover" picture is complete.

What this is *not*: a production PKI. One self-signed CA
(`certs/generate-certs.sh`), no rotation, no revocation, ~2-year
validity. That's the right amount of complexity to prove app<->Collector
mTLS is wired correctly end to end; replace `certs/` with cert-manager
or a managed CA before this leaves a single trusted host - see the risk
register below.

### Sampling vs. the health-check aggregation pattern - same problem, different answer

Both mechanisms exist to stop 100%-fidelity telemetry from becoming
unaffordable, and it's worth being explicit about why they're solved
differently:

- **Health checks** run on a fixed, predictable cadence (every 2s,
  regardless of user traffic) and what you care about is the *aggregate
  statistic* - success rate, p95 latency over the last minute - not any
  individual probe. So `HealthMonitor` keeps 100% of the population and
  reduces it deterministically: 30 checks -> 1 exact summary, every
  single time, with no randomness and no data loss for the numbers that
  matter (the aggregate is exact, not estimated).
- **Chat requests** are user-driven, bursty, and - critically - each one
  is individually valuable for debugging ("why did *this* user's session
  go wrong?"). You don't want an aggregate here, you want to be able to
  open one real trace. So the lever is probabilistic sampling: keep a
  random subset of *complete* traces at full fidelity, drop the rest
  entirely, rather than keeping 100% of requests at reduced fidelity.

Put differently: aggregate first when only the population statistic
matters (health); sample the population when individual instances matter
but you can't afford all of them (user traces). Using the wrong one the
other way round - sampling health checks (you'd get a statistically
noisy success rate) or aggregating chat traces (you'd lose the ability
to debug one user's bad session) - is the mistake to avoid.

## Health check sampling (requirement #3)

`HealthMonitor` (`app/health/monitor.py`) runs an internal probe every
`HEALTH_CHECK_INTERVAL_SECONDS` (default 2s) - config sanity, in-memory
store reachability. Individual checks are **not** exported as spans or
logged at INFO; they're buffered. Every `HEALTH_SUMMARY_WINDOW_SECONDS`
(default 60s) the buffer is reduced to one `health.summary_1m` span plus
one INFO log line: total checks, success rate, avg/min/max/p95 latency.
That's 30 checks/minute compressed into 1 exported unit - the ratio you
want before this hits a real observability bill.

Failures still surface immediately via a local WARNING log (not
exported per-check) so `docker compose logs -f app` gives you real-time
visibility without waiting for the next window.

Two read endpoints:
- `GET /health/live` - last single probe (for a load balancer / k8s liveness probe)
- `GET /health/summary` - last aggregated window (what actually reaches Langfuse/LangSmith)

## LLM endpoint (requirement #4)

`POST /chat` - litellm targets OpenRouter via the `openrouter/<provider>/<model>`
model-string convention (e.g. `openrouter/meta-llama/llama-3.1-8b-instruct`),
verified against litellm's OpenRouter provider docs. Conversation history
is a per-`session_id` in-memory deque (`app/llm/memory.py`, capped at 20
turns) - swap for Redis/Postgres without touching the graph or tracing code.

- `GET /chat/{session_id}/history`
- `DELETE /chat/{session_id}` - clear a session

## Testing

```bash
pip install -r requirements.txt -r requirements-dev.txt
python3 -m pytest tests/ -v
```

116 tests, no external services required - no live OpenRouter call, no
running Collector/Prometheus/Docker. Everything is either a pure unit
test or an in-process integration test:

| File | Covers |
|---|---|
| `test_config.py` | `Settings` defaults, validation bounds (`trace_sampling_ratio`, `observability_provider`) |
| `test_auth.py` | API-key parsing, RBAC permission checks, fail-open behavior, `authenticate()` dependency |
| `test_rate_limit.py` | `TokenBucketRateLimiter` (burst, refill-over-time, 429 + `Retry-After`, per-key isolation), `get_rate_limiter()` singleton |
| `test_redaction.py` | `RegexPIIDetector` (all 6 entity types + no-false-positive/no-name-detection checks), `redact()` (field-level replacement, overlap merging, custom detector), `PIIRedactionLogFilter`, `RedactingSpanExporter` (string-only redaction, delegation to the wrapped exporter) |
| `test_sampling.py` | `ForceTraceSampler` baggage-based override logic |
| `test_health_monitor.py` | Probe aggregation, 1-minute summary windows, p95 latency calculation |
| `test_metrics.py` | `AppMetrics` counters/histograms via an in-memory `MetricReader` |
| `test_chain.py` | LangGraph chat flow with `litellm.completion` mocked out |
| `test_routes.py` | Full FastAPI `TestClient` integration - auth/RBAC, force-trace, rate limiting, input validation, chat happy/error paths |
| `test_collector_config.py` | Structural checks on the Collector/Prometheus/compose YAML (catches a typo'd processor/exporter name without needing a live Collector) |

`test_routes.py` sets required env vars (`API_KEYS`, `OBSERVABILITY_PROVIDER=console`,
etc.) at **module import time**, before `from app.main import app` runs -
`Settings` is resolved once, cached via `lru_cache`, so it has to be
right before the app object is built. `test_config.py` explicitly clears
those same env vars in an autouse fixture, since pytest imports every
test module during collection (before any test body runs) and would
otherwise see `test_routes.py`'s values leak into its own
default-value assertions.

One harmless warning at teardown is expected and can be ignored:

```
Exception while exporting metrics
...
ValueError: I/O operation on closed file.
```

This fires because `OBSERVABILITY_PROVIDER=console` in tests, and the
console metric exporter's background export thread tries one last
flush after `TestClient`'s context manager has already closed stdout
for that test process - cosmetic, not a real failure (no assertions
touch it, and every test still passes).

### Code style

```bash
python3 -m ruff check app/ tests/
```

[Ruff](https://docs.astral.sh/ruff/) config lives in `pyproject.toml`:
`line-length = 110` (not ruff's default 88 - this codebase deliberately
favors long, explanatory inline comments over terse code + separate
docs; 110 was picked by measuring the actual violation count at several
widths, not guessed), `target-version = "py311"` (matches the
Dockerfile), and one rule (`B008`, "function call in default argument")
disabled outright because it's a false positive against FastAPI's own
`Depends(...)` dependency-injection pattern, not a real bug. Currently
clean (`All checks passed!`) - a few individual lines carry a targeted
`# noqa` with a one-line reason (e.g. `S104` on `host = "0.0.0.0"`,
correct for a containerized service) rather than a blanket rule
disable, so the exception is visible exactly where it applies.

## Project layout

```
app/
  main.py                    FastAPI app, lifespan wiring (traces + metrics + health monitor + auth log)
  config.py                  pydantic-settings, provider enum, sampling ratio, TLS + API key settings
  observability/
    setup.py                 TracerProvider + exporter selection + sampler + TLS credentials (the switch)
    metrics.py                MeterProvider + exporter selection + TLS credentials, AppMetrics instruments
    tracing.py                traced_span() helper, gen_ai.* attribute setters, set_llm_content_attributes()
    sampling.py                ForceTraceSampler (X-Force-Trace via Baggage, wraps the ratio sampler)
    redaction.py                PII redaction Layers 1/4: PIIDetector protocol, RegexPIIDetector,
                                 redact(), RedactingSpanExporter, PIIRedactionLogFilter
  security/
    auth.py                    API-key auth + RBAC (chat / force_trace permissions), app/chat* only
    rate_limit.py               per-API-key token bucket rate limiter (OWASP LLM10)
  health/
    monitor.py                2s probe loop + 60s sampling/aggregation (span + metrics)
  llm/
    chain.py                  LangGraph graph: load_memory -> llm_generate -> persist_memory
    memory.py                  in-memory per-session history
  api/
    routes.py                  /chat*(authed), /health/live, /health/summary (open)
collector/
  otel-collector-config.yaml       plaintext (default): traces (Langfuse/LangSmith/debug) + tail_sampling
                                    rate limiting, metrics (Prometheus/debug)
  otel-collector-config.tls.yaml   same pipelines, mTLS on the OTLP/HTTP receiver + TLS on the
                                    Prometheus exporter - used by docker-compose.tls.yml only
  prometheus.yml                   scrape config, plaintext (default)
  prometheus.tls.yml               scrape config, HTTPS - used by docker-compose.tls.yml only
certs/
  generate-certs.sh                self-signed CA + server (collector) + client (app) cert generator -
                                    run before docker-compose.tls.yml; generated keys/certs are gitignored
docker-compose.yml             app + otel-collector + prometheus (plaintext, default)
docker-compose.tls.yml         overlay: mTLS app<->collector, TLS collector<->prometheus (opt-in)
Dockerfile
requirements.txt
requirements-dev.txt          pytest, PyYAML, ruff - dev/test/lint only
pyproject.toml                 ruff config (line-length, target-version, rule selection)
.env.example
docs/
  SECURITY-PLAN.md            full research, current-state audit, and phased plan behind this section
```

## Known limitations (honest notes, not marketing)

- This ships a **reference/teaching implementation**, not a hardened
  production service. Auth exists now (API-key + RBAC) but is
  fail-open if `API_KEYS` is unset. Per-key request-rate limiting on
  `/chat` is now in place (`app/security/rate_limit.py`, default
  30 req/min) but it's **in-memory and single-replica**: run more than
  one app container and each replica enforces its own independent
  budget, so the effective limit becomes `rate * replica_count` - swap
  for a Redis-backed limiter before scaling out. Also still missing:
  persistence beyond process memory, retry/circuit-breaker around the
  OpenRouter call, and any prompt-injection-specific input screening
  (only blank/oversized-message rejection exists today - see OWASP
  LLM01 in the risk register below).
- The `health_monitor`'s component checks are cheap/local by design
  (config presence, store reachability) to avoid hammering OpenRouter
  every 2 seconds. If you want a real synthetic upstream check, add a
  low-cost model ping behind a longer interval than the liveness loop -
  don't put a paid LLM call on a 2s cadence.
- LangSmith OTLP attribute coverage note above - verify in your own
  LangSmith project before treating it as a like-for-like Langfuse swap.
- No local Langfuse/LangSmith stack is bundled (both are heavy multi-
  service stacks). This compose file assumes you're using their cloud
  offerings; point `LANGFUSE_HOST` at a self-hosted instance if you run
  one.
- Metrics only reach a real backend (Prometheus) in
  `OBSERVABILITY_PROVIDER=collector` mode - `langfuse_direct` and
  `langsmith_direct` print metrics to stdout only, since neither vendor
  ingests OTLP metrics today. See "Metrics pipeline" above.
- No Grafana dashboard is bundled - Prometheus's own UI/API at `:9090`
  is enough to run the example query, but you'd want Grafana for
  anything you show to a team.
- TLS/mTLS (`docker-compose.tls.yml`) is off by default and uses a
  throwaway self-signed CA with no rotation story - see "Transport
  security" above for exactly what it does and doesn't cover.
- API keys live in a plaintext env var, compared in-memory, no
  hashing/rotation/expiry - see "Access control" above and the risk
  register below (this is Phase 1 scope, deliberately narrow).
- PII redaction: Layers 1/2/4 (telemetry + logs - regex-based, structured
  PII only: emails, phone numbers, credit cards, SSNs, API-key-shaped
  strings, IPv4) are built and verified end-to-end. Regex **cannot**
  catch unstructured PII - person names, street addresses, anything with
  no fixed shape - that's a different class of detection (NER, not
  pattern matching), which is exactly Presidio's value proposition and
  exactly why Layer 3 exists as a documented future option (see "PII
  redaction" below) rather than something regex could ever fully close.
  Layer 3 itself (masking what reaches OpenRouter/conversation memory,
  not just telemetry) is still deferred.

## PII redaction

Structured PII (emails, phone numbers, credit cards, SSNs, API-key-shaped
strings, IPv4 addresses) is redacted before it leaves this process or
reaches a log aggregator, via three independent layers - a leak has to
get past all three, not just one:

- **Layer 1 - `RedactingSpanExporter`** (`app/observability/redaction.py`).
  Wraps whichever span exporter `OBSERVABILITY_PROVIDER` builds and
  redacts every string-valued span attribute before the wrapped exporter
  ever sees it - deliberately broader than "only content fields," since
  `app.session_id` is user-suppliable with no format constraint and
  could carry PII on its own. Deferred to `BatchSpanProcessor`'s
  background export thread (see "Sampling vs. health-check aggregation"
  below for the same on/off-request-path distinction) - zero added
  `/chat` latency for every network exporter; only `console` mode
  (dev-only) pays the sub-millisecond cost inline.
- **Layer 2 - Collector `redaction` processor** (`collector/otel-collector-config.yaml`
  and the `.tls.yaml` variant, kept identical). Allowlist mode: only
  explicitly listed attribute keys survive at all, anything else is
  dropped outright. This is the backstop for content that reaches a span
  through a path Layer 1 never sees - a future third-party
  auto-instrumentation hook, or a processor swap that bypasses
  `RedactingSpanExporter`. Deliberately excludes `http.target`/`http.url`
  (contain the *resolved* request path, which can embed a user-chosen
  `session_id`) and `net.peer.ip` (the caller's IP - PII under GDPR, no
  operational need for it here).
- **Layer 4 - `PIIRedactionLogFilter`** (`app/observability/redaction.py`,
  registered on the root logger in `main.py`). Runs the same `redact()`
  over every formatted log message before emission - safety net for a
  future debug line that shouldn't exist but eventually will.

**What this does not cover (Layer 3, deferred):** none of the above
touches what actually reaches OpenRouter or gets written to
`app/llm/memory.py` - only telemetry and logs are redacted. Masking the
live request/response (litellm's native Presidio guardrail) stays Phase
3, deferred pending a concrete need, since it changes application
behavior (the model sees masked text), not just observability.

**Regex vs. Presidio - the pluggable seam.** Detection is regex-based
today (`RegexPIIDetector`), which is fast (~25-800us per call depending
on message length, see `docs/SECURITY-PLAN.md` Section 2.3) and catches
structured PII, but **cannot** catch unstructured PII - person names,
street addresses, anything without a fixed shape - because that requires
NER (a model), not pattern matching. `redact()` and every layer above it
only depend on the `PIIDetector` protocol
(`app/observability/redaction.py`), never on regex specifics:

```python
class PIIDetector(Protocol):
    def detect(self, text: str) -> List[PIIMatch]: ...
```

Adding Presidio later means implementing this one method (wrapping
`presidio_analyzer.AnalyzerEngine().analyze()`, mapping its results to
`PIIMatch`) and changing `get_pii_detector()` to return it - nothing in
`RedactingSpanExporter`, `PIIRedactionLogFilter`, or
`set_llm_content_attributes()` would need to change. Worth knowing before
flipping that switch: Presidio's own maintainers report ~10-25ms per
call (vs. <1ms for regex) and a ~560MB spaCy model dependency - see
`docs/SECURITY-PLAN.md` Section 2.3 for the full cost comparison.

## Security

Full research, current-state audit, and phased rollout plan live in
[`docs/SECURITY-PLAN.md`](docs/SECURITY-PLAN.md) - this section is the
condensed, always-current-with-shipped-code table form of that plan.
Every status below reflects what's actually in this codebase right now,
verified against the files cited in "Addressed by," not the plan's
aspirations - where something is planned but not built, it says so.

### Risk register

Every risk identified during the security review, what it is, whether
it's mitigated today, and what's still open. `In place` links to the
code that addresses it; `Not covered` links to what would address it
once built (tracked in `docs/SECURITY-PLAN.md`).

| Risk | Description | Status | How it's addressed / what's planned | Addressed by / reference |
|---|---|---|---|---|
| Unauthenticated `/chat` access | Anyone reaching the port could call the LLM (and spend your OpenRouter budget) with no credential at all | **In place** | API-key auth required on `POST/GET/DELETE /chat*`, RBAC via a `chat` permission. Fail-open if `API_KEYS` is unset (loud startup warning, not silent) | `app/security/auth.py`, "Access control" above |
| Unrestricted `X-Force-Trace` abuse | Forcing full-fidelity tracing is also forcing extra Collector/backend load per request - without a gate, any caller could use it to inflate observability cost | **In place** | Header only honored if the caller's API key carries the separate `force_trace` permission; otherwise silently ignored (not rejected) | `app/security/auth.py`, `app/api/routes.py`, "Force-sampling a specific request" above |
| API keys stored/compared insecurely | Naive string comparison leaks timing info; plaintext-in-env-var storage has no rotation/expiry/hashing | **Not covered** (partially - see next column) | Comparison IS constant-time (`secrets.compare_digest`) - that part's done. Hashing, rotation, and expiry are not; explicitly Phase 3 scope (`docs/SECURITY-PLAN.md` item 11), excluded from this pass by design | `app/security/auth.py` (compare_digest); SECURITY-PLAN.md Phase 3 item 11 |
| Observability pipeline overload under load | A traffic spike could linearly spike trace volume/cost with it, or blow up Collector memory | **In place** | Collector `tail_sampling` processor: always-keep-errors + `rate_limiting` (spans/sec token bucket), off the request path entirely | `collector/otel-collector-config.yaml`, "Load-based sampling" above |
| Request-level rate limiting / cost control | Nothing stops an authenticated-but-unrated caller from calling `/chat` in a tight loop and running up OpenRouter spend - this is distinct from the observability rate limit above, which only protects the trace pipeline | **In place** | Per-API-key token bucket, `RATE_LIMIT_REQUESTS_PER_MINUTE` (default 30/min), 429 + `Retry-After` when exhausted. In-memory/single-replica by design - see "Known limitations" | `app/security/rate_limit.py`, `app/api/routes.py` |
| Blank/empty-message spam | `min_length=1` alone lets a single space through - free LLM calls (and spend) for zero-content input | **In place** | Pydantic `field_validator` rejects whitespace-only `message` with a 422 before the request reaches the LLM runner | `app/api/routes.py::ChatRequest.message_must_not_be_blank` |
| Head-sampling silently defeating tail-based error preservation | Setting `TRACE_SAMPLING_RATIO<1.0` in collector mode would make some error traces never reach the Collector to be evaluated at all | **In place** | Startup warning fires if this misconfiguration is detected; default ratio is `1.0` specifically to keep this correct | `app/observability/setup.py::_build_sampler` |
| Plaintext OTLP: app <-> Collector | Trace/metric payloads (once Layer 1-4 content capture exists) would cross this hop unencrypted, unauthenticated at the transport level | **In place** (opt-in) | mTLS overlay - `docker-compose.tls.yml` + `certs/generate-certs.sh`. Off by default so the base path stays zero-config | "Transport security" above |
| Plaintext scrape: Collector -> Prometheus | Metrics scrape traffic unencrypted between the two containers | **In place** (opt-in) | Same TLS overlay covers this leg (`collector/prometheus.tls.yml`) | "Transport security" above |
| Egress: Collector -> Langfuse/LangSmith | Trace export leaving the Docker network to a third-party SaaS | **Not applicable** | Already TLS - both are `https://` endpoints regardless of the overlay above; nothing to add | "Transport security" above |
| PII captured in span attributes | `app.session_id` is user-suppliable with no format constraint - a user could put an email or anything else in it, and any future prompt/completion capture would carry PII too | **In place** | `RedactingSpanExporter` regex-redacts every string-valued span attribute (not just content-designated ones) before it leaves the process, deferred to the export thread - zero added `/chat` latency. Verified end-to-end: an email embedded in `session_id` came out as `[EMAIL]` across every span in the trace | `app/observability/redaction.py::RedactingSpanExporter`, "PII redaction" below |
| PII via third-party auto-instrumentation | A future LangChain/litellm OTel hook, or any span processor added later that bypasses `RedactingSpanExporter`, could attach content through a path Layer 1 never sees | **In place** | Collector `redaction` processor, allowlist mode - only explicitly allowed attribute keys pass through at all; deliberately excludes `http.target`/`http.url` (embed the resolved request path) and `net.peer.ip` (caller IP, PII under GDPR) | `collector/otel-collector-config.yaml` (`processors.redaction`), "PII redaction" below |
| PII reaching the model provider / stored in memory | Text a user pastes into a message reaches OpenRouter and persists in `app/llm/memory.py`, independent of what telemetry captures | **Not covered** (deferred) | litellm's native Presidio guardrail, explicitly deferred to Phase 3 unless a concrete need shows up in practice - the only layer that can't be built as pure defense-in-depth around the existing request path, since it has to change what's actually sent | Not yet built - `docs/SECURITY-PLAN.md` Section 2.1, Layer 3 |
| PII via ad hoc debug logging | A future `logger.debug(f"...{message}...")` added during troubleshooting ships raw PII to stdout/log aggregators | **In place** | `PIIRedactionLogFilter` registered on the root logger - runs the same `redact()` over every formatted log message before emission, regardless of which logger emitted it | `app/observability/redaction.py::PIIRedactionLogFilter`, "PII redaction" below |
| Container runs as root | Dockerfile has no `USER` directive - a container escape has root inside the container as a head start | **Not covered** | Planned, cheap fix (`docs/SECURITY-PLAN.md` Phase 1 item 4) | Not yet built |
| No dependency/image CVE scanning | Pinned versions (`requirements.txt` uses `==`) don't mean vulnerability-free | **Not covered** | Planned: `pip-audit` + image scan (Phase 2 item 8) | Not yet built |
| Internal ports published to host | Prometheus `:9090` and Collector `:8889` are bound to the host by default for local convenience - not appropriate if this ever runs on a shared/internet-facing host | **Not covered** | Planned: make host publishing opt-in via an override file (Phase 2 item 9) | Not yet built |

### OWASP Top 10 for LLM Applications - applicability to this service

**On "2026":** verified via search - there is no separate 2026 edition
of the OWASP Top 10 *for LLM Applications*; the 2025 edition (v2.0,
released Nov 2024) is still current as of this writing and is what's
mapped below. OWASP did release a related but distinct **[Top 10 for
Agentic Applications (2026)](https://genai.owasp.org/llm-top-10/)**
("ASI Top 10") - not mapped here since this service has no agentic/tool-calling
behavior today, but worth revisiting if that changes (see LLM06 row).

| Risk | Description | Status | Notes | Addressed by / reference |
|---|---|---|---|---|
| **LLM01:2025** Prompt Injection | Crafted input that the model follows as an instruction rather than data, because prompt and data share one channel | Partially in place | Basic guardrail only: whitespace/empty-message rejection, `max_length=4000`. No prompt-injection-specific detection/sanitization - that's a much larger, model-behavior-dependent control, not attempted here. Low blast radius today - no tool-calling/agency in the current graph | `app/api/routes.py::ChatRequest` |
| **LLM02:2025** Sensitive Information Disclosure | PII/secrets leaking through model output, logs, or telemetry | Partially in place | Layers 1/2/4 (telemetry + logs) are built and verified end-to-end - see the risk register above. Layer 3 (what actually reaches OpenRouter/`app/llm/memory.py`) is still deferred, so PII in the model call/conversation history itself remains open | `app/observability/redaction.py`, `collector/otel-collector-config.yaml` |
| **LLM03:2025** Supply Chain | Vulnerable/malicious dependencies, models, or data sources in the build | Not covered | Dependency pinning is in place (`requirements.txt`); CVE/image scanning is not | [OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/) |
| **LLM04:2025** Data and Model Poisoning | Training data or fine-tuning tampered with to bias/backdoor the model | Not applicable | No training/fine-tuning or data-ingestion pipeline in this service - OpenRouter's hosted models are called via API only | [OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/) |
| **LLM05:2025** Improper Output Handling | Model output trusted/rendered without the same scrutiny as any other untrusted input | Not covered | `assistant_message` returns as a raw JSON field; safe rendering is the caller's responsibility, not enforced here | [OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/) |
| **LLM06:2025** Excessive Agency | Model granted more autonomous capability (tools, permissions) than a task needs | Not applicable | No tool-calling or autonomous action in the current graph (`load_memory -> llm_generate -> persist_memory` only) - revisit if that changes | [OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/) |
| **LLM07:2025** System Prompt Leakage | System prompt assumed secret but extracted and found to contain access-control logic or credentials | In place | `SYSTEM_PROMPT` in `app/llm/chain.py` is already generic and non-secret - correct by construction, not by a technical control | `app/llm/chain.py` |
| **LLM08:2025** Vector and Embedding Weaknesses | Embedding/retrieval pipeline manipulated to poison or exfiltrate via a RAG store | Not applicable | No vector store, embeddings, or RAG pipeline in this service | [OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/) |
| **LLM09:2025** Misinformation | Confident, plausible, wrong model output presented as fact | Not applicable (for this pass) | Inherent LLM hallucination risk; mitigations are prompt-engineering/grounding concerns, not the infra/security-plumbing scope of this pass | [OWASP LLM Top 10](https://genai.owasp.org/llm-top-10/) |
| **LLM10:2025** Unbounded Consumption | Uncontrolled resource/cost usage - DoS or runaway spend | In place | Per-API-key token bucket rate limiter (default 30 req/min) on `/chat`, plus Collector-side `tail_sampling` `rate_limiting` protecting the observability pipeline itself. Spend is also visible via `app.llm.cost_usd_total` | `app/security/rate_limit.py`, `collector/otel-collector-config.yaml` |

## Suggested next steps (for the AI Architect track)

1. Point Grafana at the bundled Prometheus and build a dashboard for
   `app.chat.requests_total`, `app.llm.cost_usd_total` rate, and
   `app.health.success_rate` - the metrics already exist, this is purely
   a visualization exercise.
2. Replace the in-memory store with Redis and add a `node.load_memory`
   cache-hit/miss attribute (and a matching metric) - good exercise in
   keeping trace *and* metric instrumentation stable while swapping an
   implementation detail underneath.
3. Try `langsmith_direct` mode and compare what LangSmith infers from
   `gen_ai.*` attributes vs. Langfuse - a concrete way to internalize
   why semantic-convention support varies by vendor.
4. Add an OTel Logs pipeline (the third signal, alongside traces and
   metrics) so `logging.getLogger` output is correlated with trace_id/
   span_id automatically instead of only via the manual `app.response.
   trace_id` attribute this service sets today.
5. Build the 4-layer PII redaction plan (risk register above) -
   `app/observability/redaction.py` first, since Layers 2-4 all lean on
   the same `redact()` function.
6. Swap the in-memory rate limiter (`app/security/rate_limit.py`) for a
   Redis-backed one before running more than one app replica - today
   each replica enforces its own independent budget.
7. Non-root `Dockerfile` user, `pip-audit`/image CVE scanning, and
   making Prometheus/Collector host-port publishing opt-in - all cheap,
   all still open (risk register above).
