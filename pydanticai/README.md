# Weather Intelligence Agent

A lightweight, low-latency weather service with a PydanticAI natural-language
agent, a NiceGUI UI, SQLite persistence, an APScheduler-driven daily
collection job, and end-to-end OpenTelemetry observability.

Weather is always retrieved for a precise city, station, or coordinate —
never an unspecified point representing an entire country or state. State
representative results are always labeled as such.

## Architecture at a glance

```
Client → FastAPI → WeatherService → in-memory cache → Open-Meteo   (never touches the LLM)
Client → FastAPI → PydanticAI agent → typed tool → WeatherService → Open-Meteo
UI (NiceGUI, mounted at /ui) → same application services, in-process, no HTTP hop
Scheduler → BatchService → Open-Meteo → SQLite (weather_observations)
```

- **Provider**: `OpenMeteoWeatherProvider` — general Forecast API
  (`models=best_match`) worldwide, or MeteoSwiss
  (`models=meteoswiss_icon_seamless`) only for locations inside a configured
  Switzerland/Liechtenstein bounding box. (`models=auto` — sometimes cited
  as the default in docs summaries — is actually rejected by the live API;
  verified via a 400 response.)
- **Cache**: bounded in-memory TTL cache with request coalescing.
  Single-replica limitation — see [Known limitations](#known-limitations-and-scale-out-path).
- **Persistence**: SQLite (WAL mode) via SQLAlchemy 2 async + Alembic.
- **Scheduler**: in-process APScheduler, checks every location's local time
  against its own IANA timezone; single-replica limitation, see below.
- **Observability**: OpenTelemetry traces (OTLP → otel-collector → Tempo),
  with Collector-side tail sampling (always keep failed-request traces,
  sample a configurable percentage of successful ones — see
  [Sampling](#sampling)), Prometheus metrics (`/metrics` on its own port,
  `9464` by default, separate from the main app port — see
  `app/observability/metrics.py` for why this isn't a second OTLP
  pipeline, and why it's a separate port), structured JSON logs with
  trace/span/request/job IDs.
- **Security**: demo-grade — IP-based rate limiting (10/min by default),
  JWT auth with a DB-backed user/role store gating the `force_trace`
  sampling override; `/v1/*` business endpoints remain unauthenticated.
  See [Authentication](#authentication) and FAQ #18.

Full phased design rationale, corrected assumptions, and trade-offs are in
the project's design conversation; this README covers running, using, and
troubleshooting what was built.

## Project structure

```
app/
  api/            FastAPI routers: v1 (locations, weather, history, agent, auth),
                  internal (job trigger + user creation, token-protected), health
  agent/          PydanticAI agent, typed tools, schemas
  application/    Service layer: weather, location, history, batch, auth
  domain/         Framework-free models, protocols, errors
  infrastructure/
    database/     SQLAlchemy models, repositories, session/WAL setup, seed data
    llm/          (LiteLLM Proxy is reached via PydanticAI's OpenAI-compatible provider)
    weather/      Open-Meteo provider, HTTP client, in-memory cache
  observability/  Tracing (+ tail-sampling-aware sampler), Prometheus metrics,
                  structured logging, request-context middleware
  security/       IP rate limiting, password hashing, JWT issuance (demo-grade)
  scheduler/      APScheduler wiring, end-of-day trigger logic
  ui/             NiceGUI UI (pages.py: layout/wiring) + callbacks.py (pure data ops)
  config/         pydantic-settings
tests/
  unit/           Fast, no I/O beyond SQLite temp files; respx for HTTP mocking
  integration/    Full FastAPI app via TestClient, real temp SQLite DB
  load/           Standalone load-test script (not part of pytest)
alembic/          Migrations
docker/           Dockerfile, entrypoint, otel-collector/prometheus/tempo/loki configs
dashboards/       Grafana provisioning + dashboard JSON
```

## Quickstart

### Docker Compose (recommended)

```bash
cp .env.example .env
# edit .env: set OPENROUTER_API_KEY, and change the default secrets
# (SECURITY__INTERNAL_API_TOKEN, LITELLM_MASTER_KEY, SECURITY__JWT_SECRET)
# before anything but local demo use
docker compose up --build
```

- UI: http://localhost:8000/ui — open, no login required. A login form
  exists at `/ui/login` (linked from the top-right of the home page) for
  getting a bearer token; it doesn't gate anything else in the UI — see
  [Authentication](#authentication).
- API docs: http://localhost:8000/docs
- Metrics: `9464` inside the Docker network only (e.g. `docker exec` into
  another container and `curl weather-app:9464/metrics`) — deliberately not
  published to the host by default; uncomment the port mapping in
  `docker-compose.yml` for local `curl localhost:9464/metrics` debugging.
- Auth: no default account. Uncomment `SECURITY__BOOTSTRAP_ADMIN_USERNAME`/
  `_PASSWORD` in `.env` before first `up` for a ready-to-use login, or
  create one via the API — see [Authentication](#authentication).

Add heavier observability tooling (Prometheus, Grafana, Tempo) with a profile:

```bash
docker compose --profile observability up --build
```

- Grafana: http://localhost:3000 (admin / value of `GF_SECURITY_ADMIN_PASSWORD`, default `admin`)
- Prometheus: http://localhost:9090

An `observability-watchdog` container also comes up with this profile: it
polls `weather-app`'s running state and stops grafana/prometheus/tempo/
otel-collector once `weather-app` has been down for
`WATCHDOG_GRACE_PERIOD_SECONDS` (default `600` = 10 min) — no point running
the observability stack for an app that isn't up. It does **not** restart
anything when `weather-app` comes back; that's still a manual
`docker compose up`. Verified live: with a 30s test grace period, stopping
`weather-app` correctly stopped all four dependents ~31s later. Needs the
Docker socket to call `docker stop` on sibling containers — effectively
root-equivalent access to the whole Docker daemon, accepted here as a
local-demo-only trade-off (see `docker/observability-watchdog.sh` and
[Known limitations](#known-limitations-and-scale-out-path)).

Optional log aggregation:

```bash
docker compose --profile observability --profile optional-loki up --build
```

### Local development (no Docker)

Requires `uv` and Python 3.12+ (uv will provision the interpreter).

```bash
uv sync --dev
uv run alembic upgrade head
uv run python -m app.infrastructure.database.seed
uv run uvicorn app.main:app --reload
```

Agent queries need a reachable LiteLLM Proxy — either run one locally
(`uv run litellm --config litellm_config.yaml --port 4000`, with
`OPENROUTER_API_KEY` set) or leave `AGENT__LITELLM_BASE_URL` pointed at a
running one. Every other capability (locations, current weather, history,
batch, UI) works without it.

## Configuration

All settings are environment-driven, `__`-nested (`pydantic-settings`). See
[.env.example](.env.example) for the complete list with defaults. Key ones:

| Variable | Purpose |
|---|---|
| `DATABASE__URL` | SQLite connection string (WAL mode enabled automatically) |
| `CACHE__CURRENT_WEATHER_TTL_SECONDS` | Current-weather cache TTL |
| `AGENT__LITELLM_BASE_URL` / `AGENT__LITELLM_API_KEY` | LiteLLM Proxy endpoint + virtual key |
| `AGENT__MODEL_ALIAS` / `AGENT__FALLBACK_MODEL_ALIAS` | Must match `litellm_config.yaml`'s `model_name` entries |
| `OPENROUTER_API_KEY` | Used by `litellm-proxy` (the container), not by `weather-app` directly |
| `SCHEDULER__ENABLED` | Set `false` to disable the in-process scheduler (e.g. for tests, or when running >1 replica) |
| `SECURITY__INTERNAL_API_TOKEN` | Required as `X-Internal-Token` header on `/internal/*` |
| `SECURITY__ALLOW_DIRECT_COORDINATES` | Disable raw lat/lon weather lookups if desired |
| `SECURITY__RATE_LIMIT_ENABLED` / `_REQUESTS_PER_MINUTE` | IP-based rate limit, default on, 10/min |
| `SECURITY__JWT_SECRET` / `_ALGORITHM` / `_EXPIRES_MINUTES` | Demo-grade JWT auth signing key/algorithm/TTL |
| `SECURITY__FORCE_TRACE_ROLE` | Role required to use the `force_trace` sampling override |
| `OBSERVABILITY__OTEL_ENABLED` | Set `false` to skip trace export (e.g. no collector running) |
| `OTEL_TAIL_SAMPLING_BASELINE_PERCENT` | Collector-side (not app-nested) - % of *successful* traces kept; failures always kept |

## REST API examples

### curl

```bash
curl http://localhost:8000/v1/locations/countries

curl "http://localhost:8000/v1/locations/states?country_code=IN"

curl "http://localhost:8000/v1/locations?country_code=IN&state_code=TG"

curl "http://localhost:8000/v1/weather/current?location_id=hyderabad"

curl "http://localhost:8000/v1/weather/current?latitude=17.385&longitude=78.4867&timezone=Asia/Kolkata"

curl "http://localhost:8000/v1/weather/current/state?country_code=IN&state_code=TG"

curl -X POST http://localhost:8000/v1/agent/query \
  -H "Content-Type: application/json" \
  -d '{"message": "Should I carry an umbrella in Hyderabad today?"}'

curl "http://localhost:8000/v1/weather/history?location_id=hyderabad&start_date=2024-01-01&end_date=2024-01-31&page=1&page_size=20"

curl -X POST http://localhost:8000/internal/jobs/daily-weather \
  -H "X-Internal-Token: change-me-internal-token"

curl http://localhost:8000/internal/jobs/daily-weather/<job_id> \
  -H "X-Internal-Token: change-me-internal-token"

# --- Auth (see the Authentication section above) ---
curl -X POST http://localhost:8000/internal/auth/users \
  -H "X-Internal-Token: change-me-internal-token" -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "correct horse battery staple", "role": "trace_admin"}'

curl -X POST http://localhost:8000/v1/auth/login -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "correct horse battery staple"}'

curl http://localhost:8000/v1/auth/me -H "Authorization: Bearer <access_token>"

curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready

# /metrics is on its own port (9464), not published to the host by default -
# see docker-compose.yml. From inside the Docker network:
#   docker compose exec otel-collector wget -qO- http://weather-app:9464/metrics
```

### Windows PowerShell

```powershell
Invoke-RestMethod http://localhost:8000/v1/locations/countries

Invoke-RestMethod "http://localhost:8000/v1/weather/current?location_id=hyderabad"

Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/agent/query `
  -ContentType "application/json" `
  -Body (@{ message = "Should I carry an umbrella in Hyderabad today?" } | ConvertTo-Json)

Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/jobs/daily-weather `
  -Headers @{ "X-Internal-Token" = "change-me-internal-token" }

Invoke-RestMethod http://localhost:8000/health/ready
```

## Testing

```bash
uv run pytest tests/ -v
```

115 tests: provider mapping/retries (respx-mocked, no real network), cache
hit/miss/coalescing, the low-latency path proven to never invoke the agent,
location resolution (representative/ambiguous/missing), batch idempotency
and overlap-prevention, agent tool contracts and structured-output failure
handling (via PydanticAI's `FunctionModel` — no real LLM call), OTel span
parent/child relationships (in-memory exporter), metric-label cardinality,
UI callback contracts, and Docker Compose config validation.

### Load test

```bash
uv run uvicorn app.main:app &
uv run python tests/load/load_test.py --base-url http://localhost:8000 --requests 50 --concurrency 10
```

Compares uncached vs. cached current-weather latency, the UI page-shell load
time, an agent query, and one daily-collection run — reporting p50/p95/p99,
throughput, and error rate per operation. Agent and uncached-weather numbers
require a reachable LiteLLM Proxy and outbound internet to Open-Meteo
respectively; without them the tool still runs to completion and reports the
resulting error rate honestly rather than crashing. Note the UI number is
page-shell load time, not a full interactive round trip — NiceGUI's actual
click/dropdown interactions run over a stateful Socket.IO session per
browser client, which isn't practically replayable from a stateless script;
see the comment in `tests/load/load_test.py` for the reasoning.

## Observability

- **Traces**: FastAPI, httpx, SQLAlchemy, and PydanticAI (`Agent.instrument_all()`)
  are all auto-instrumented; `weather_service.py` and `batch_service.py` add
  explicit application-level spans. Exported via OTLP/HTTP to `otel-collector`,
  which forwards to Tempo (`--profile observability`). View them in Grafana's
  Tempo datasource (Explore → Tempo → TraceQL), or query the collector's
  `debug` exporter output in its container logs.
- **Metrics**: `GET /metrics`, Prometheus text format, served on its own
  port (`OBSERVABILITY__METRICS_PORT`, default `9464`) via
  `prometheus_client`'s own WSGI server — deliberately not a FastAPI route,
  so it can be firewalled independently of the public API/UI port (see
  `app/observability/metrics.py`). In `docker-compose.yml` the port is
  reachable to other containers on `weather-net` (e.g. `prometheus`) but not
  published to the host. Scraped directly by Prometheus
  (`--profile observability`) — see `docker/prometheus.yml`. Dashboards:
  `dashboards/grafana/dashboards/*.json`, auto-provisioned into Grafana
  under the "Weather Intelligence Agent" folder.
- **Logs**: structured JSON to stdout, with `trace_id`/`span_id`/`request_id`/
  `correlation_id`/`job_id` on every line, including a `"request completed"`
  line for every request (not just errors) — pivot from a log line straight
  to its trace.

### Correlation IDs

Two independent IDs, both on every request/response and every span in that
request's trace:

- **`request_id`** — always app-generated, identifies one HTTP hop/UI
  action. Header: `X-Request-ID`.
- **`correlation_id`** — caller-controlled, meant to be reused across many
  requests. Defaults to a fresh UUID if not supplied. Header:
  `X-Correlation-ID` for REST callers; the UI shows and lets you edit it
  directly at the top of the page.

Both are propagated as OTel [Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/)
(see `app/observability/correlation.py`, `middleware.py`), which a
`BaggageSpanProcessor` (in `tracing.py`) copies onto *every* span in the
trace — not just the root — so a TraceQL `select()` works on any span:

```
{ resource.service.name = "weather-intelligence-agent" } | select(span.correlation_id)
```

### Authentication

Minimal, demo-grade JWT auth (`app/security/`) exists for exactly one
purpose today: gating the `force_trace` sampling override by role (see
[Sampling](#sampling) below). It is *not* wired into `/v1/*` business
endpoints, which remain open — see
[Known limitations](#known-limitations-and-scale-out-path).

**There is no default user out of the box.** No account is seeded
automatically — a hidden, guessable default credential would undercut the
"minimal but honest" security stance more than not having one at all.
Two ways to get a user:

1. **Bootstrap one from `.env`** (recommended for local use) — set
   `SECURITY__BOOTSTRAP_ADMIN_USERNAME` and `_PASSWORD` (both commented out
   by default in `.env.example`); on the next `docker compose up`/restart
   the app creates that user if it doesn't already exist yet — idempotent,
   safe to leave set permanently, and it never resets the password on
   subsequent restarts. `SECURITY__BOOTSTRAP_ADMIN_ROLE` defaults to
   `trace_admin`.
2. **Create one via the API** — `POST /internal/auth/users`, protected by
   the same `X-Internal-Token` shared secret as `/internal/jobs/*` rather
   than open self-signup (sidesteps "who's allowed to create the first
   admin" by reusing a secret operators already need for batch jobs).

- **`users` table** — `username`, `password_hash` (PBKDF2-HMAC-SHA256,
  100k iterations, per-user salt — stdlib `hashlib`, no bcrypt/passlib
  dependency), `role` (free-form string; the only value this app checks
  anywhere is `SECURITY__FORCE_TRACE_ROLE`, default `trace_admin`).
- **`POST /v1/auth/login`** — `{"username", "password"}` → a bearer JWT
  (`SECURITY__JWT_SECRET`/`_ALGORITHM`/`_EXPIRES_MINUTES`, single shared
  HS256 key, no rotation or revocation).
- **`GET /v1/auth/me`** — `Authorization: Bearer <token>` → `{username, role}`,
  mainly for verifying a token came out right.
- **`/ui/login`** — a browser form for the same login, linked from the home
  page's top-right corner. Not an auth *wall*: every other `/ui` page still
  works without logging in, matching the API's own open-by-default scope
  (only the "Trace" checkbox below is unlocked by it). On success the
  token is stored in NiceGUI's `app.storage.user` - a server-side dict
  keyed by a signed browser cookie (`SECURITY__UI_STORAGE_SECRET`, distinct
  from `JWT_SECRET`) - and the browser is sent back to the weather app,
  now showing "Signed in as \<user\> (\<role\>)" with a logout link.
- **"Trace" checkbox** — next to the Correlation ID field on the home page.
  When checked by a signed-in `trace_admin` user, the next action's trace
  is forced through regardless of sampling, the same way the `baggage`
  header does for REST callers (`app/observability/correlation.py`'s
  `correlation_scope` sets the identical `force_trace`/`auth_token` baggage
  keys in-process) - see [Sampling](#sampling). Disabled with an
  explanatory tooltip for anyone not signed in with that role; the
  Correlation ID field and this checkbox's state persist in the same
  session storage across page loads.

```bash
# Option 1: uncomment SECURITY__BOOTSTRAP_ADMIN_USERNAME/_PASSWORD in .env,
# then just log in - no extra API call needed:
curl -X POST http://localhost:8000/v1/auth/login -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "change-me-admin-password"}'

# Option 2: create a user explicitly via the internal-token-protected API
curl -X POST http://localhost:8000/internal/auth/users \
  -H "X-Internal-Token: change-me-internal-token" -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "correct horse battery staple", "role": "trace_admin"}'

curl -X POST http://localhost:8000/v1/auth/login -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "correct horse battery staple"}'
```

### Sampling

Sampling is deliberately split across two layers, because "keep every
failed request's trace, sample only a percentage of successful ones" is a
decision that literally cannot be made correctly at span-*start* time (the
outcome isn't known yet):

- **App SDK (head sampling, `app/observability/sampling.py`)** — handles
  the two decisions that *don't* depend on the eventual outcome:
  - `/health/live` and `/health/ready` are polled far more often than real
    traffic and carry little diagnostic value per call, so they're
    rate-limited to at most one sampled trace per
    `OBSERVABILITY__HEALTH_CHECK_SAMPLE_INTERVAL_SECONDS` (default `300`,
    i.e. 5 minutes; set `60` for a tighter window while debugging).
  - Everything else is forwarded to the collector unconditionally
    (`ParentBased(ALWAYS_ON)`) — there is no app-side sampling-ratio
    setting for ordinary traffic anymore; see below.
- **OTel Collector (tail sampling, `docker/otel-collector-config.yaml`)** —
  buffers each trace for `decision_wait` (10s), then decides: any trace
  containing a `status.code=ERROR` span is *always* kept; everything else
  is kept at `OTEL_TAIL_SAMPLING_BASELINE_PERCENT` (a plain `.env` var,
  default `100` = keep successful traces too — lower it to actually shed
  volume from healthy traffic without ever risking a dropped failure).
  Note this only catches spans FastAPI/httpx mark `ERROR` — by OTel
  semantic convention that's 5xx/unhandled exceptions, not routine 4xx
  (a 404 for an unknown location, a 401 from a bad token, a 429 from the
  rate limiter are not "failures" in this sense and are subject to the
  normal baseline percentage like any other successful-in-the-tracing-sense
  request).

**Force-trace override, with RBAC.** A caller can force one specific
request to be sampled regardless of the above — but unlike a normal
protected endpoint, this can't be checked via `Authorization: Bearer` or
any FastAPI dependency, because by the time those run the span (and the
sampling decision) already exists. The only hook point that runs *before*
`should_sample()` is the W3C `baggage` propagator, so both the override
flag and the caller's JWT have to travel there instead. From the UI, the
"Trace" checkbox (see [Authentication](#authentication)) does this for
you; from curl:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "correct horse battery staple"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -H "baggage: force_trace=true,auth_token=$TOKEN" http://localhost:8000/health/live
```

A forced span is also tagged `force_traced=true`, and the Collector's
`tail_sampling` policies OR this attribute in alongside `errors-always` and
`baseline-probabilistic` — without it, a forced trace could still be
silently dropped by a baseline below 100%, which would make the "force" a
lie. Verified live: at `OTEL_TAIL_SAMPLING_BASELINE_PERCENT=0`, an ordinary
request was dropped while a `force_trace` one (with a valid `trace_admin`
token) was kept.

The sampler verifies the JWT's signature and checks its `role` claim
against `SECURITY__FORCE_TRACE_ROLE` (default `trace_admin`) — a bad
signature, expired token, missing token, or wrong role all silently fall
through to normal sampling (a sampling decision must never raise). Once
the span exists, `RequestContextMiddleware` immediately scrubs
`auth_token` back out of the OTel baggage context — see its comment for
why: left in place, the same baggage propagator that makes this trick work
would carry the JWT into this app's own outgoing httpx calls (Open-Meteo,
LiteLLM), leaking a bearer credential to third parties. (A custom header
name can't hook into the sampling *decision* itself, for the same reason
`force_trace` can't: verified against the installed instrumentation's
source, custom-header capture adds a header to the span only *after* the
sampler has already run.)

Exceptions are marked for filtering at every layer: spans get
`status.code=ERROR` + an `exception` event automatically (OTel SDK default,
which is what the tail-sampling policy above keys off), Prometheus has
dedicated failure counters (`open_meteo_failures_total`,
`agent_runs_total{status="failure"}`, `batch_locations_total{result="failure"}`,
etc.), and `logger.exception(...)` calls put the full traceback in the JSON
log's `exc_info` field.

## Troubleshooting

**`docker compose up` fails on `litellm-proxy` health check.**
Usually a missing/invalid `OPENROUTER_API_KEY` in `.env`. Check
`docker compose logs litellm-proxy` — LiteLLM logs a clear auth error.
Everything except `/v1/agent/query` works without it.

**`/v1/weather/current` returns 502.**
Open-Meteo is unreachable or timing out. Check `HTTP_CLIENT__*` timeout
settings and outbound network from the container. This is the intended
failure mode (never a fabricated reading) — see `WeatherProviderError`
handling in `app/application/weather_service.py`.

**`/v1/agent/query` times out or 504s.**
Check `litellm-proxy` is healthy (`docker compose ps`) and
`AGENT__MODEL_ALIAS`/`AGENT__FALLBACK_MODEL_ALIAS` match `litellm_config.yaml`'s
`model_name` entries exactly. Raise `AGENT__TOTAL_LATENCY_BUDGET_SECONDS` if
the model is genuinely just slow (free-tier OpenRouter models can queue).

**`/internal/jobs/daily-weather` returns 401.**
Missing or wrong `X-Internal-Token` header — must match
`SECURITY__INTERNAL_API_TOKEN`.

**`/internal/jobs/daily-weather` returns 409.**
A run is already active. Check `GET /internal/jobs/daily-weather/{job_id}`
for its status; if it's been "running" for longer than
`SCHEDULER__STALE_RUN_TIMEOUT_SECONDS`, the next trigger attempt will
automatically mark it abandoned and proceed.

**SQLite "database is locked" under load.**
WAL mode allows one writer at a time; watch `sqlite_busy_errors_total`.
Raise `DATABASE__BUSY_TIMEOUT_MS` first. Sustained contention is a signal
you've outgrown a single-writer SQLite setup — see scale-out path below.

**UI page loads but looks broken / a JS error mentions `svelte.js`.**
That was the previous Gradio-based UI (replaced with NiceGUI after a
reproducible frontend crash — `Cannot read properties of undefined
(reading 'addEventListener')` inside Gradio's own bundled Svelte runtime,
confirmed present even with a minimal Gradio app and with every custom
component isolated out, i.e. not caused by this project's code). If you
see this, you're on a stale build — `docker compose up --build` to pick up
the NiceGUI UI in `app/ui/pages.py`.

**UI page loads but a dropdown doesn't update after selecting another one.**
Cascading dropdowns (`Country → State → Location`) are wired via
`select.on_value_change(...)` in `app/ui/pages.py`, calling `set_options()`
on the dependent dropdown. If you add a new cascading field, follow the
same pattern - `on_country_change`/`on_state_change` in
`_build_current_weather_tab`.

**Structured JSON logs show `trace_id: "000...0"`.**
Tracing is disabled (`OBSERVABILITY__OTEL_ENABLED=false`) or no span is
active for that log line — this is the documented fallback in
`TraceContextFilter`, not a bug.

## Production-readiness checklist

- [x] Request/coordinate/timezone/date-range/pagination validation
- [x] Internal endpoint authentication (`X-Internal-Token`)
- [x] Graceful shutdown (uvicorn SIGTERM → FastAPI lifespan → scheduler,
      DB engine, tracer provider all shut down in order)
- [x] Non-root Docker user, multi-stage build, no dev tools in runtime image
- [x] Pinned dependencies (`uv.lock`) and pinned image tags everywhere (no `:latest`)
- [x] Readiness check (`/health/ready`, verifies DB connectivity)
- [x] No stack traces in API/UI responses (`HTTPException` details only;
      UI callbacks catch and show friendly messages)
- [x] Idempotent daily collection (UPSERT on `location_id + observation_date + provider + collection_type`)
- [x] Overlap prevention + stale-run recovery for the batch job
- [x] Rate limiting — `IPRateLimitMiddleware` (`app/security/rate_limit.py`),
      a 60s sliding window per client IP, default 10 requests/minute
      (`SECURITY__RATE_LIMIT_ENABLED` / `_REQUESTS_PER_MINUTE`), exempting
      `/health/live`, `/health/ready`, and anything under `/ui` or
      `/_nicegui` (a single UI page load fires 15+ background requests for
      NiceGUI's own static assets/socket.io client - none of that is
      user-driven API traffic the limiter is meant to police; verified
      live that without this exemption the UI became unusable after one
      page load). In-memory per process - see
      [Known limitations](#known-limitations-and-scale-out-path) on
      single-replica scope; needs a shared store (e.g. Redis) behind >1
      replica or worker.
- [x] JWT auth + RBAC — minimal, demo-grade (see the
      [Authentication](#authentication) section below): a `users` table
      (username/password hash/role), `POST /internal/auth/users` to create
      one (or `SECURITY__BOOTSTRAP_ADMIN_USERNAME`/`_PASSWORD` to seed one
      at startup), `POST /v1/auth/login` to get a bearer JWT, `GET
      /v1/auth/me` to inspect it, and `/ui/login` for the same from a
      browser (session stored in NiceGUI's `app.storage.user`). The only
      thing currently gated by role is the `force_trace` sampling override
      (`trace_admin` role required) - a "Trace" checkbox on the home page
      for signed-in users, or the `baggage` header for curl. `/v1/*`
      business endpoints remain unauthenticated - see below.
- [ ] Multi-user auth on `/v1/*` — only `force_trace` is role-gated; the
      rest of `/v1/*` remains open. This is a single-user local demo,
      by explicit design; see limitations below.
- [ ] Secrets management — `.env` file only. Fine for local demo; use a real
      secrets manager before any shared deployment.
- [ ] TLS — none; terminate TLS at a reverse proxy before any non-localhost use.

## Known limitations and scale-out path

- **In-memory cache is single-replica.** A second `weather-app` instance
  gets its own cache and its own in-flight-request coalescing — no
  cross-replica coherence. Scale-out path: swap `InMemoryWeatherCache` for
  a Redis-backed implementation of the same `WeatherCache` protocol
  (`app/domain/protocols.py`) — nothing else changes.
- **In-process APScheduler is single-replica.** Running >1 replica with the
  scheduler enabled means every replica independently fires the same
  end-of-day check — not corrupting (idempotent UPSERT + run-overlap lock
  absorb it) but wasteful and log-noisy. Scale-out path: set
  `SCHEDULER__ENABLED=false` on all but one replica, or replace with an
  external scheduler (cron container, workflow engine) calling
  `POST /internal/jobs/daily-weather` on exactly one instance.
  A crashed process mid-run leaves a `"running"` row; the
  `stale_run_timeout_seconds` heuristic auto-recovers from this, at the
  cost of not detecting a *genuinely* still-running-but-slow job as such
  until that timeout elapses.
- **SQLite is single-writer.** Fine for one scheduler + a read-heavy API;
  a multi-writer production workload should move to Postgres —
  `infrastructure/database/repositories.py` and the SQLAlchemy models are
  the only places that would need to change (dialect-specific UPSERT syntax
  differs).
- **No horizontal-scale session affinity for the UI.** NiceGUI keeps
  per-session state server-side over a Socket.IO connection; a load
  balancer without sticky sessions would break mid-interaction. Not a
  concern for the intended single-replica local deployment.
- **`observability-watchdog` has Docker-socket access.** It mounts
  `/var/run/docker.sock` (read-write, not `:ro` — `docker stop` calls need
  it) to stop sibling containers, which is effectively root-equivalent
  access to the whole Docker daemon. Acceptable for a local demo profile;
  would need a scoped Docker API proxy (e.g. a socket-permission gateway)
  before this pattern belonged in anything shared.
- **Metrics/traces are two separate pipelines by design** (Prometheus pull
  for metrics, OTLP push for traces) — see `app/observability/metrics.py`'s
  module docstring for the reasoning. If a unified OTLP metrics pipeline is
  ever needed, add an OTel `MeterProvider` alongside the existing
  `TracerProvider` in `tracing.py`.
- **This session's sandboxed test environment had unreliable outbound
  internet** to Open-Meteo and no running LiteLLM Proxy, so live end-to-end
  numbers for uncached-weather/agent load-test operations couldn't be
  captured here — the load-test script itself is verified working (handles
  both success and failure paths cleanly); real numbers need a normal
  network environment.

## Solution Architect FAQ

Questions a reviewing architect would actually ask, answered with the real
reasoning behind each decision — not the generic textbook version.

**1. Why PydanticAI over LangChain (or LangGraph/CrewAI) for the agent layer?**
Four concrete reasons, not a general preference:
- **Structured output is native, not bolted on.** `output_type=AgentQueryResult` (a plain Pydantic model) is validated automatically — no separate output-parser step, no manual JSON-mode prompt wrangling. The spec required "a validated Pydantic result model"; that's PydanticAI's actual design surface, not an adapter over it.
- **Tools are typed Python functions.** `resolve_supported_location(ctx, query: str)` — PydanticAI derives the tool's JSON schema from the signature. No separate tool-schema DSL to keep in sync with the implementation.
- **First-class deterministic testing.** `FunctionModel`/`TestModel` script the model's tool-calling behavior without a network call, while still exercising the real agent loop (retries, schema validation, tool dispatch). This is how Phase 7 got tested end-to-end with zero LLM calls and zero flakiness.
- **Built-in OTel instrumentation** (`Agent.instrument_all()`) follows OpenTelemetry's GenAI semantic conventions out of the box — no separate LangSmith/wrapper integration needed to get agent-run and tool-call spans.

Where LangChain still wins: a large pre-built ecosystem (retrievers, document loaders, hundreds of integrations) for RAG-heavy pipelines, or LangGraph specifically for complex, stateful multi-agent workflows with branching control flow. This project has neither of those needs — one agent, six tools, one structured output — so PydanticAI's narrower, more stable surface was the better fit. (Worth noting: a sibling project in this same workspace explicitly moved *away* from LangChain's community LiteLLM wrapper because its tool-calling support "varies by version" and hand-rolled a direct integration instead — the same instability shows up in practice, not just in theory.)

**2. Why NiceGUI over Streamlit, and why did the original Gradio choice get replaced?**
The spec required the UI to mount *in-process* into the existing FastAPI app (`no separate UI container`). NiceGUI is built on FastAPI/Starlette and does this natively via `ui.run_with(app, mount_path="/ui")`. Streamlit fundamentally cannot — it only runs as its own standalone server process; embedding it would need a subprocess + reverse proxy or an iframe, a real architectural mismatch. Gradio was the original choice (and the spec's literal suggestion) but was replaced after finding a reproducible frontend crash — `functools.partial`-wrapping an async-generator callback broke Gradio's internal dispatch, confirmed via a minimal reproduction with no custom code involved. NiceGUI's imperative, direct-DOM-mutation model also turned out simpler for this app's needs than Gradio's declarative inputs/outputs wiring.

**3. Why SQLite instead of Postgres?**
The actual write load is one scheduled batch job plus occasional manual triggers — a single writer, well within SQLite's WAL-mode capability (concurrent readers, one writer). Postgres would be infrastructure with no measured requirement behind it for this workload. The repository layer (`infrastructure/database/repositories.py`) is the only place that would need to change for a Postgres migration — domain and application code have no SQL-dialect awareness.

**4. Why an in-memory cache instead of Redis?**
Same reasoning as #3: no measured multi-replica requirement yet. The `WeatherCache` protocol (`domain/protocols.py`) is deliberately provider-neutral — swapping in a Redis-backed implementation is an infrastructure-layer change, not a domain-layer one. Documented explicitly as a single-replica limitation rather than silently assumed away.

**5. Why run LiteLLM Proxy as a separate container instead of calling OpenRouter directly from the app?**
Two reasons: it keeps the real `OPENROUTER_API_KEY` out of the application process entirely (the app only holds a virtual key), and it decouples model routing/fallback from application code — `AGENT__FALLBACK_MODEL_ALIAS` is a config change in `litellm_config.yaml`, not a code change. The trade-off is a real extra network hop, which is why it's used *only* on the agent path and never on the deterministic weather path.

**6. Why APScheduler in-process instead of Celery/Airflow/an external scheduler?**
This is a single-replica local deployment by explicit scope — a full workflow engine would be infrastructure without a demonstrated requirement. The trade-off is documented, not hidden: running >1 replica with the scheduler enabled means every replica independently fires the same check (harmless — idempotent UPSERT + DB overlap lock absorb it — but wasteful). The documented migration path is disabling it on all but one replica, or replacing it with an external trigger hitting the same internal endpoint.

**7. Why does `/metrics` use `prometheus_client` directly instead of routing through the OTel Collector?**
Running both an OTLP metrics pipeline and Prometheus's native pull-scrape would be two metrics paths for one app with no measured benefit. Traces are naturally push/aggregation-friendly (spans generated deep in call stacks, better collected centrally); metrics are naturally pull-friendly with Prometheus's model. This is a stated trade-off in `metrics.py`'s module docstring, not an oversight — if a unified OTLP metrics pipeline is ever needed, it's an additive change (a `MeterProvider` alongside the existing `TracerProvider`), not a rewrite.

`/metrics` also lives on its own port (`9464` by default, `OBSERVABILITY__METRICS_PORT`) via `prometheus_client.start_http_server()`, not as a FastAPI route on the main app port. That's deliberate: it means the metrics endpoint can be firewalled to internal-only access (e.g. left off `docker-compose.yml`'s published ports, reachable only by other containers on the Docker network such as Prometheus) purely at the network layer, with zero application code involved — no auth middleware needed on `/metrics` specifically, and no risk of accidentally exposing it alongside the public API/UI.

**8. Why FastAPI over Flask/Django?**
Async-native (the entire weather/agent/batch path is `async def` end to end — sync I/O on the event loop was an explicit constraint to avoid), Pydantic v2 integration for request/response validation matching the same validation library used throughout the domain layer, and automatic OpenAPI docs at `/docs` satisfying the deliverable requirement directly.

**9. Why the layered `domain/application/infrastructure` structure instead of a flatter, simpler layout?**
The spec explicitly required the ability to replace SQLite, Open-Meteo, Gradio (later NiceGUI), and LiteLLM without rewriting domain logic — that's only true if domain code has zero framework/infrastructure imports. `domain/protocols.py`'s `WeatherProvider`/`WeatherCache` Protocols are what made the Gradio→NiceGUI swap, and would make a Postgres or Redis swap, purely additive changes at the infrastructure layer.

**10. Why Open-Meteo instead of a commercial weather API?**
No API key required for the core forecast endpoints (lower friction for a local demo), genuinely free tier with no rate-limit surprises during development, and it offers both a general worldwide model blend and region-specific high-resolution models (MeteoSwiss) through the same API shape — which let the provider-selection requirement (worldwide vs. regional) be demonstrated with one integration instead of two.

**11. How is low latency actually *guaranteed* on the deterministic weather path, not just typically fast?**
Structurally: `/v1/weather/current` has no import of the agent module at all — the low-latency guarantee isn't "the agent is usually fast," it's "the agent literally cannot be invoked from this path." Enforced by a test that breaks the agent on purpose and confirms the weather endpoint is unaffected. Layered on top: bounded retries with backoff, a total-latency budget via `asyncio.wait_for`, an in-memory TTL cache, and per-key request coalescing (concurrent requests for the same location share one upstream call, verified by asserting the mock upstream is called exactly once under concurrent load).

**12. What actually stops the agent from fabricating a location or weather value?**
The agent's *only* data access is through typed tools that call the same application services the REST API uses — `resolve_supported_location` returns exclusively DB-backed candidates, `get_current_weather` returns exclusively live-fetched or explicitly-errored data. There is no code path for the model to invent a `location_id` string and have it accepted downstream. The system prompt reinforces this, but the enforceable guarantee is structural, independent of what the model "decides" to do.

**13. Why OTel Baggage for correlation-ID propagation instead of just setting a span attribute?**
`span.set_attribute()` only affects the one span it's called on — verified directly against a live trace that attributes set only on the root span never appeared on child spans (httpx, SQLAlchemy, application spans), since OTel doesn't propagate arbitrary attributes to children automatically. Baggage is the mechanism designed for exactly this: it lives in the OTel Context, and a `BaggageSpanProcessor` copies allow-listed keys onto every span created while that context is active — confirmed by pulling a real trace and checking every span's attributes.

**14. Why a custom `Sampler` for health-check traces instead of the standard percentage-based one?**
Percentage sampling doesn't bound absolute frequency — a health check polled every 15 seconds still produces steady volume at any nonzero ratio. A rate-limited sampler (≤1 sample per N seconds, forwarding everything else unconditionally) bounds it directly. The force-trace override deliberately uses the W3C `baggage` header rather than a custom header name, because custom-header capture in the installed instrumentation happens *after* the sampling decision — verified against the instrumentation's own source, not assumed. It's also RBAC-gated: `force_trace=true` alone isn't enough anymore, the caller must also carry a JWT (in baggage, under a separate key, for the same before-the-decision reason) whose `role` claim matches `SECURITY__FORCE_TRACE_ROLE`. See the [Sampling](#sampling) section for the full mechanism, including why the JWT is scrubbed from baggage immediately after the span is created.

**15. What's the horizontal scale-out story, given SQLite + in-memory cache + in-process scheduler?**
None of the four (adding the IP rate limiter to the original three) block scaling, but none are free either — each has a documented single-point-of-change: `WeatherCache` protocol swap for a distributed cache, a config flag (`SCHEDULER__ENABLED=false`) plus an external trigger for the scheduler, a dialect change in the repository layer for the database, and `IPRateLimitMiddleware`'s in-memory per-process bucket would need a shared store (e.g. Redis) to enforce one true limit across replicas rather than each replica enforcing its own. The OTel Collector's tail-sampling processor adds a fifth: it needs every span of a trace to land on the *same* collector instance to decide correctly, so it'd need a load-balancing exporter in front of >1 collector replica. The architecture was built so these are additive infrastructure swaps, not domain rewrites — but they are real gaps today, not hypothetically-solved ones.

**16. Why `uv` instead of pip/poetry/pipenv?**
Reproducible builds via `uv.lock`, fast enough to make `uv sync --frozen` in the Docker builder stage cheap to re-run, and a single tool for dependency resolution, virtualenv management, and script execution (`uv run`) — fewer moving parts in both local dev and CI/Docker than juggling separate lockfile and environment tools.

**17. Why multi-stage Docker build with a non-root user — what does that actually mitigate?**
Multi-stage keeps `uv` itself and any build-time-only artifacts out of the runtime image (smaller attack surface, smaller image). Non-root means a container-escape or dependency-RCE scenario doesn't hand over root inside the container. Neither is theoretical box-ticking — the Dockerfile's `HEALTHCHECK` and the entrypoint's `exec` (not a shell wrapper) around the final `uvicorn` command were specifically chosen so SIGTERM reaches the app directly for graceful shutdown, verified by checking the lifespan's shutdown sequence actually runs (scheduler → HTTP client → DB engine → tracer provider, in order).

**18. What's the actual security posture, and what's explicitly not done?**
Done: internal-endpoint token auth, IP-based rate limiting (10/min by default, exempting health checks), demo-grade JWT auth with a DB-backed user/role store, request/coordinate/timezone/pagination/date-range validation, no stack traces in API or UI responses, secrets only via `.env` (never committed). Explicitly *not* done, called out rather than hidden: `/v1/*` business endpoints are not auth-protected (only the `force_trace` sampling override is role-gated — single-user local-demo scope by design); the rate limiter is in-memory per-process (no shared store, so it's per-replica, not global); JWTs use a single shared HS256 secret with no rotation/revocation and passwords are PBKDF2 (not bcrypt/argon2's memory-hardness); no TLS (expects a reverse proxy in front for any real exposure). An architect reviewing this should treat the checklist in this README as the actual state, not aspirational.

**19. Why respx/`FunctionModel`-based testing instead of hitting real external services in tests?**
Determinism and speed — the full 100+-test suite runs in under 30 seconds with zero network calls, zero API keys, and zero flakiness from a third party being slow or down. Every external dependency (Open-Meteo via `respx`, the LLM via `FunctionModel`, Docker Compose via `docker compose config` with a CLI-availability skip) is faked at the *protocol* boundary, not the business-logic boundary — so the tests still exercise real retry logic, real schema validation, real provider-selection logic.

**20. What would you change first to support 10x traffic or multi-tenancy?**
Not the cache — a duplicated in-memory cache under more replicas just costs a slightly worse hit rate, self-limiting rather than correctness-breaking. The scheduler first: every replica independently firing the same end-of-day collection is wasteful and log-noisy today, and would get worse linearly with replica count. After that: SQLite → Postgres (the write path would start to matter at 10x), then the in-memory cache → Redis (to restore cross-replica hit rates and request coalescing, and to give the rate limiter one true shared counter instead of one per replica). Multi-tenancy would additionally need real auth on `/v1/*` (today only `force_trace` is role-gated) and per-tenant rate limits rather than one global bucket per IP.

**21. Why does creating a user require the internal token instead of open self-signup?**
This app has exactly one thing gated by role today (the `force_trace` sampling override), so a full signup/verification/approval flow would be infrastructure for a permission that barely exists yet. Reusing `X-Internal-Token` — the same secret operators already need for `/internal/jobs/*` — sidesteps the usual "who's allowed to create the first admin" bootstrap problem for free, at the cost of anyone holding that one shared secret being able to mint accounts with any role, including `trace_admin`. Acceptable for the demo/single-operator scope this app targets; a real multi-tenant version would need a proper admin role separate from the internal-automation token.

**22. Why does the `force_trace` JWT travel via the `baggage` header instead of the normal `Authorization` header?**
Because by the time a normal `Authorization` header would be checked — a FastAPI `Depends`, or even Starlette middleware — the span already exists and the sampling decision is final; `should_sample()` runs before any of that, with only the OTel Context (populated by the `traceparent`/`baggage` propagator) available to inspect. `app/observability/sampling.py` verifies the JWT's signature and `role` claim synchronously, no DB/network call, right there in the sampler. The trade-off is real and is treated as one, not hidden: putting a bearer credential in baggage means it would otherwise ride the same propagator into this app's own outgoing httpx calls to Open-Meteo/LiteLLM — `RequestContextMiddleware` explicitly strips it back out of the OTel Context immediately after span creation to close that off, since by then it's already done its one job.

**23. Why move ordinary-traffic sampling to the OTel Collector instead of keeping it in the app's own `Sampler`?**
Because "keep every failed request, sample a percentage of successful ones" needs the eventual HTTP status/exception, which doesn't exist yet at span-*start* time — no head sampler, custom or built-in, can make that call correctly. The SDK now forwards ordinary traffic unconditionally (`ParentBased(ALWAYS_ON)`); the Collector's `tail_sampling` processor buffers each trace for `decision_wait` (10s) and decides after the fact, based on whether any span in the trace has `status.code=ERROR`. The cost is real, not hidden: buffering adds Collector-side memory and a decision-wait window, and it only works with every span of a trace landing on the same collector instance — see Q15 on what that means for scale-out.
