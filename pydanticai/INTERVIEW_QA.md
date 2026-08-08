# Weather Intelligence Agent — 50 Interview Questions & Answers

Answered from the perspective of the person who built and defended this
system, not textbook definitions. Grounded in the actual codebase
(`app/`), the README's FAQ/Known-limitations sections, and — where a claim
is about a third-party library's internals rather than this project's own
code — verified against current documentation (sources at the bottom).

Ordered most-critical-and-must-know first, within seven sections:
Solution Architecture, Security, Observability, Python Language, Frameworks
& Libraries, Testing, Concurrency & Performance.

---

## Section 1 — Solution Architecture (most critical)

**Q1. Walk me through the high-level architecture in 60 seconds.**
Two entry paths, one deterministic core. A REST client with a known
`location_id` calls `WeatherService` directly — cache, then Open-Meteo,
never touching an LLM. A natural-language client goes through a PydanticAI
agent whose only job is resolving free text to a `location_id` via a typed
tool call, then it hits the identical `WeatherService`. Separately, an
in-process APScheduler runs an end-of-day batch job that persists daily
observations to SQLite, independent of either request path. Everything is
wrapped in OpenTelemetry tracing, Prometheus metrics on a separate port,
and structured JSON logs — all mounted in one FastAPI process, including
the NiceGUI UI (`ui.run_with(app, mount_path="/ui")`, no separate
container).

**Q2. What's the single architectural decision you'd defend hardest?**
That the LLM never touches weather data directly. `get_current_weather`
and `resolve_supported_location` are typed tools that call the *same*
application services the REST API uses — there is no code path by which
the model can fabricate a location or a reading, because there's no
channel for it to invent one through. This is enforced structurally (a
test breaks the agent module on purpose and confirms `/v1/weather/current`
is unaffected), not just requested via the system prompt.

**Q3. Why PydanticAI over LangChain/LangGraph/CrewAI?**
Four concrete reasons: structured output is native (`output_type=`, no
separate output-parser step); tools are plain typed Python functions
(schema derived from the signature, nothing to keep in sync); first-class
deterministic testing via `FunctionModel`/`TestModel` (scripts the model's
tool-calling behavior with zero network calls, while still exercising
retries and schema validation); and built-in OTel instrumentation
(`Agent.instrument_all()`) following GenAI semantic conventions out of the
box. LangChain still wins for RAG-heavy pipelines with many integrations,
or LangGraph for complex branching multi-agent workflows — this project
has one agent, six tools, one structured output, so PydanticAI's narrower
surface was the better fit, not a universally "better" library.

**Q4. How is low latency actually *guaranteed* on the deterministic path,
not just typically fast?**
Structurally: the weather router has no import of the agent module at
all — enforced by a test, not a convention. On top of that: bounded
retries with backoff, a total-latency budget via `asyncio.wait_for`, an
in-memory TTL cache, and per-key request coalescing (concurrent requests
for the same location share one upstream call — verified by asserting the
mock upstream is hit exactly once under concurrent load).

**Q5. Why the layered `domain/application/infrastructure` structure
instead of something flatter?**
The spec required swapping SQLite, Open-Meteo, the UI framework
(Gradio→NiceGUI happened mid-build), and the LLM proxy without rewriting
domain logic — only true if domain code has zero framework imports.
`domain/protocols.py`'s `WeatherProvider`/`WeatherCache` Protocols are
what made the UI swap, and would make a Postgres/Redis swap, purely
additive infrastructure-layer changes.

**Q6. Why SQLite instead of Postgres, and when would that stop being
true?**
The actual write load is one scheduled batch job plus occasional manual
triggers — a single writer, well within SQLite's WAL-mode capability
(concurrent readers, one writer). It stops being true under sustained
multi-writer load; `sqlite_busy_errors_total` is the metric to watch, and
`infrastructure/database/repositories.py` is the only layer that would
need to change (dialect-specific UPSERT syntax differs) — domain and
application code have no SQL-dialect awareness.

**Q7. Why an in-memory cache instead of Redis?**
Same reasoning as SQLite: no measured multi-replica requirement. The
`WeatherCache` protocol is provider-neutral by design, so swapping in a
Redis-backed implementation is an infrastructure change, not a
domain-layer one. Documented explicitly as a single-replica limitation,
not silently assumed away.

**Q8. What's the actual horizontal scale-out story?**
Four single-replica shortcuts, each with a documented single point of
change: the in-memory cache (swap the `WeatherCache` protocol
implementation), the in-process scheduler (`SCHEDULER__ENABLED=false` on
all but one replica, or an external trigger calling
`POST /internal/jobs/daily-weather`), SQLite (dialect change in the
repository layer), and the in-memory rate-limit bucket (needs a shared
store like Redis so replicas enforce one true limit instead of one each).
The OTel Collector's tail-sampling processor adds a fifth: it needs every
span of a trace to land on the same collector instance, so a
load-balancing exporter would be needed in front of >1 collector replica.

**Q9. What would you change first to support 10x traffic?**
Not the cache — a duplicated in-memory cache under more replicas just
costs a slightly worse hit rate, self-limiting rather than
correctness-breaking. The scheduler first: every replica independently
firing the same end-of-day check gets linearly worse with replica count.
Then SQLite→Postgres (write path starts to matter), then the cache→Redis
(restores cross-replica hit rate and gives the rate limiter one true
shared counter).

**Q10. Why run the LLM proxy (LiteLLM) as a separate container instead of
calling OpenRouter directly?**
Keeps the real `OPENROUTER_API_KEY` out of the application process
entirely (the app only holds a virtual key), and decouples model
routing/fallback from application code —
`AGENT__FALLBACK_MODEL_ALIAS` is a config change in `litellm_config.yaml`,
not a code change. The trade-off is a real extra network hop, which is
why it's used only on the agent path, never on the deterministic weather
path.

**Q11. Why Open-Meteo instead of a commercial weather API?**
No API key for core endpoints (lower friction for a local demo), a
genuinely free tier with no rate-limit surprises during development, and
it exposes both a general worldwide model blend and region-specific
high-resolution models (MeteoSwiss) through the same API shape — one
integration demonstrates both the worldwide and regional
provider-selection requirement instead of two.

**Q12. Describe a real bug you hit and how you found it — not a
hypothetical.**
`models=auto` was cited as Open-Meteo's default in a documentation
summary I'd researched, but the live API rejects it with a 400
("Cannot initialize MultiDomains from invalid String value auto"). Only
caught by hitting the real endpoint from inside the running container,
not by trusting the summarized research. Fixed by switching the default
to `models=best_match` and updating the code comment to say *why*, not
just *what*.

---

## Section 2 — Security

**Q13. What's the actual security posture — done vs. explicitly not
done?**
Done: internal-endpoint token auth (`X-Internal-Token`), IP-based rate
limiting (10/min default, sliding 60s window), demo-grade JWT auth with a
DB-backed user/role store, request/coordinate/timezone/pagination
validation, no stack traces in API/UI responses, secrets only via `.env`.
Explicitly not done: `/v1/*` business endpoints aren't auth-protected
(only the `force_trace` sampling override is role-gated); the rate
limiter is in-memory per-process, not a shared/global limit; JWTs use a
single shared HS256 secret with no rotation or revocation; passwords are
PBKDF2, not bcrypt/argon2's memory-hardness; no TLS. Stated as the actual
state in the README, not aspirational.

**Q14. Why PBKDF2 instead of bcrypt or argon2 for password hashing?**
PBKDF2-HMAC-SHA256 at 100k iterations with a stdlib-only implementation
(`hashlib`, no bcrypt/passlib dependency) was the pragmatic choice for a
demo-scope auth system. Honest trade-off: PBKDF2 is CPU-hard but not
memory-hard, so it's more parallelizable on GPUs/ASICs than bcrypt or
argon2, which are memory-hard by design. For anything beyond a local
demo, argon2id is the better default.

**Q15. How does the JWT-gated `force_trace` sampling override actually
work, and why can't it use a normal `Authorization` header?**
By the time a FastAPI `Depends` or even Starlette middleware would check
an `Authorization` header, the span already exists and the sampling
decision is final — `should_sample()` runs before any of that, with only
the OTel Context (populated by the `traceparent`/`baggage` propagator)
available. So both the `force_trace=true` flag and the caller's JWT travel
in the W3C `baggage` header instead. The sampler verifies the JWT
signature and `role` claim synchronously, right there — a bad signature,
expired token, missing token, or wrong role all silently fall through to
normal sampling, because a sampling decision must never raise.

**Q16. That JWT is now sitting in OTel Baggage — doesn't that leak it
downstream?**
Yes, and that's handled explicitly: once the span exists,
`RequestContextMiddleware` immediately scrubs `auth_token` back out of
the OTel Context. Left in place, the same baggage propagator that makes
the trick work would carry the JWT into this app's own outgoing httpx
calls (Open-Meteo, LiteLLM) — leaking a bearer credential to third
parties. `correlation_id` and the `force_trace` boolean stay in baggage
(not credentials, harmless to propagate); only the token is scrubbed.

**Q17. Why can't a custom header (like `X-Force-Trace`) drive the
sampling decision instead of the `baggage` header?**
Verified against the installed instrumentation's source
(`opentelemetry-instrumentation-asgi`): custom-header capture
(`http_capture_headers_server_request`) adds a header's value to the span
*after* `tracer.start_span()` has already run and the sampler has already
decided. The W3C `baggage`/`traceparent` propagators are the only
mechanism the SDK extracts into the parent `Context` *before*
`should_sample()` is called — that's a hard structural constraint, not a
style choice.

**Q18. What stops the rate limiter itself from being trivially bypassed?**
Honestly, not much at the demo-scope level — it's a per-process in-memory
sliding window keyed on `X-Forwarded-For`'s first hop or the raw ASGI
transport address, so trusting XFF is only safe behind a reverse proxy
that strips client-supplied XFF, which this app doesn't verify. That's a
documented gap, not an oversight. It does correctly exempt health checks
and `/ui`/`/_nicegui` asset traffic (verified live: without that
exemption, a single UI page load — 15+ background requests for static
assets/socket.io — exhausted the limit and broke the UI after one load).

**Q19. Why does creating a user require the internal token instead of
open self-signup?**
This app has exactly one thing gated by role today (the `force_trace`
override), so a full signup/verification flow would be infrastructure for
a permission that barely exists. Reusing `X-Internal-Token` — the same
secret operators already need for `/internal/jobs/*` — sidesteps "who's
allowed to create the first admin" for free, at the cost of anyone
holding that shared secret being able to mint accounts with any role,
including `trace_admin`. Acceptable for single-operator demo scope; a
real multi-tenant version needs a separate admin role.

**Q20. What does the multi-stage Docker build + non-root user actually
mitigate?**
Multi-stage keeps `uv` and build-time-only artifacts out of the runtime
image — smaller attack surface, smaller image. Non-root means a
container-escape or dependency-RCE scenario doesn't hand over root inside
the container. Neither is box-ticking: the entrypoint uses `exec` (not a
shell wrapper) around the final `uvicorn` command specifically so SIGTERM
reaches the app directly for graceful shutdown — verified by confirming
the lifespan's shutdown sequence (scheduler → HTTP client → DB engine →
tracer provider, in order) actually runs on stop.

---

## Section 3 — Observability & Distributed Tracing

**Q21. Why OpenTelemetry over a vendor-specific tool like LangSmith?**
OTel instruments the model call, the HTTP layer, the database, and the
scheduler under one standard — a trace shows the LLM step *and* the
deterministic process it triggered, not just the model call in isolation.
Honest caveat: OTel's GenAI-specific semantic conventions are still
marked experimental (as of this year), and attribute names can shift
between releases. LangSmith is more mature for the model call
specifically. The trade made here is standards-based, vendor-neutral
coverage of the whole system now, against some near-term spec churn.

**Q22. Why is sampling split across the app SDK *and* the OTel Collector
instead of one sampler?**
Because "keep every failed request's trace, sample a percentage of
successful ones" needs the eventual HTTP status/exception — information
that doesn't exist yet at span-*start* time. No head sampler, custom or
built-in, can make that call correctly. So the SDK forwards ordinary
traffic unconditionally (`ParentBased(ALWAYS_ON)`), and the Collector's
`tail_sampling` processor buffers each trace for a `decision_wait` window
(10s) and decides after the fact, based on whether any span in the trace
has `status.code=ERROR`.

**Q23. What's the one thing the app-side sampler still has to decide
itself, and why?**
Health-check rate limiting. `/health/live` and `/health/ready` are polled
far more often than real traffic with little diagnostic value per call, a
decision that *doesn't* depend on the eventual outcome — so it's made at
span-start via a custom `Sampler` that allows at most one sampled trace
per `HEALTH_CHECK_SAMPLE_INTERVAL_SECONDS` (default 300s), rather than a
percentage that doesn't bound absolute frequency.

**Q24. Walk me through a real bug you found in this exact pipeline.**
The Collector's `tail_sampling` processor was fully defined in
`otel-collector-config.yaml` — policies and all — but never actually
added to the pipeline's `processors` list (`[batch]` only, missing
`tail_sampling`). An earlier "verification" that a 0% baseline dropped
traces was a false positive; nothing was filtering at all. Caught by
re-reading the config file cold, fixed by adding `tail_sampling` to the
pipeline (order matters: it must run before `batch`, since it needs
individual spans grouped by trace ID), and re-verified for real — an
ordinary request was dropped at 0% baseline, a `force_trace`-tagged one
was kept.

**Q25. Why does correlation-ID propagation use OTel Baggage instead of
just `span.set_attribute()`?**
Verified directly against a live trace: an attribute set only on the root
span never appeared on child spans (httpx, SQLAlchemy, application
spans) — OTel doesn't propagate arbitrary attributes to children
automatically. Baggage lives in the OTel Context itself, and a
`BaggageSpanProcessor` copies allow-listed keys onto *every* span created
while that context is active, confirmed by pulling a real trace and
checking every span's attributes.

**Q26. Why does `/metrics` run on its own port instead of as a FastAPI
route?**
`prometheus_client.start_http_server()` runs its own lightweight WSGI
server on a separate port (9464 by default), deliberately not a FastAPI
route — so it can be firewalled independently of the public API/UI port
purely at the network layer (left off `docker-compose.yml`'s published
ports, reachable only by other containers on the Docker network). Zero
application code needed for that isolation, and no risk of accidentally
exposing it alongside the public surface.

**Q27. Why are traces and metrics two separate pipelines (OTLP push vs.
Prometheus pull) instead of unifying them through the Collector?**
Traces are naturally push/aggregation-friendly (spans generated deep in
call stacks, better collected centrally); metrics are naturally
pull-friendly with Prometheus's scrape model. Running both an OTLP
metrics pipeline and Prometheus's native pull-scrape would be two paths
for one app with no measured benefit — a stated trade-off in the code, not
an oversight. If a unified pipeline is ever needed, it's additive (an OTel
`MeterProvider` alongside the existing `TracerProvider`), not a rewrite.

**Q28. How would you prove, to a skeptical reviewer, that the
low-latency guarantee is real and not just "usually fast in testing"?**
Two things, both already in the test suite: a test that monkeypatches/
breaks the agent module and asserts the weather endpoint is completely
unaffected (proves the import boundary, not just typical timing), and the
load-test script's p50/p95/p99 comparison between cached and uncached
current-weather latency, reported honestly even when the agent/LLM proxy
isn't reachable rather than crashing.

---

## Section 4 — Python Language Features

**Q29. Why `async def` everywhere instead of sync code with a thread
pool?**
The entire weather/agent/batch path is I/O-bound (HTTP calls to
Open-Meteo/LiteLLM, SQLite queries) — async lets one process handle many
concurrent in-flight requests on a single event loop without a thread per
request. It was an explicit constraint to avoid sync I/O blocking the
event loop, since FastAPI, httpx, and SQLAlchemy's asyncio extension all
support it natively end-to-end here.

**Q30. What's actually happening under the hood when SQLAlchemy's
`AsyncSession` runs a query?**
SQLAlchemy's ORM internals are synchronous; the asyncio extension wraps
them in `greenlet` so blocking calls can yield back to the event loop when
real I/O happens, rather than truly rewriting the ORM as async. That's
why `greenlet` is a real (if usually invisible) dependency of
`sqlalchemy[asyncio]`, and why a single `AsyncSession` instance isn't safe
to share across concurrently-running tasks — it's not a purely async-native
implementation underneath.

**Q31. Explain `asyncio.wait_for` and why it's used for both the HTTP
client and the agent, not just a client-level timeout.**
`asyncio.wait_for` wraps a coroutine with a hard wall-clock deadline,
raising `TimeoutError` if it isn't done in time — independent of whatever
timeout the HTTP client itself is configured with. It's layered on top of
httpx's own per-request timeouts here because the agent path involves
*multiple* sequential calls (tool call → tool call → final model
response) whose combined time httpx's own per-call timeout can't bound;
only a budget around the whole operation can.

**Q32. What's a Python `Protocol` (structural typing) doing in
`domain/protocols.py`, and why not an abstract base class?**
`Protocol` (PEP 544) gives structural typing — anything with matching
method signatures satisfies it, no explicit inheritance required. That
matters here because `WeatherProvider`/`WeatherCache` are implemented by
infrastructure-layer classes that the domain layer must never import
(the whole point of the layered structure) — an ABC would require the
implementation to import and subclass the domain type, `Protocol` doesn't.

**Q33. Why use context managers (`contextmanager`/`asynccontextmanager`)
so heavily — `correlation_scope`, the FastAPI `lifespan`, etc.?**
Context managers guarantee cleanup runs even on exception — `finally`
semantics without repeating try/finally at every call site. It's the
right tool anywhere setup/teardown must be paired: attaching and
detaching OTel Context tokens in LIFO order, or the FastAPI app's startup
(wire services, start scheduler) and shutdown (stop scheduler, close HTTP
client, dispose DB engine, shut down the tracer) sequence.

**Q34. What Python 3.12-specific capability does this project actually
rely on, versus just requiring a recent version out of caution?**
Mostly the general async/typing maturity (`X | Y` union syntax throughout
without `from __future__ import annotations` gymnastics needed for
runtime evaluation in most spots, though it's still declared for
forward-compatibility). Nothing in this codebase depends on a 3.12-only
language feature that would break on 3.11 — the version floor here is
about ecosystem currency (uv's Python-management story) more than a hard
language dependency.

**Q35. Decorator pattern: how does `_instrumented_ui_op`/`_instrumented`
work, and why not just call the metrics functions inline in every
callback?**
Both are `functools.wraps`-preserving decorators that time a call,
increment a Prometheus counter/histogram labeled by outcome
(success/failure), and re-raise on exception after recording — applied
once per function via `@decorator` instead of duplicating
try/except/finally + metric calls at every one of a dozen call sites. One
change to the instrumentation logic (e.g., adding a new label) updates
every decorated function at once.

---

## Section 5 — Frameworks & Libraries

**Q36. Why FastAPI over Flask or Django?**
Async-native end to end (matching the async-I/O constraint above),
Pydantic v2 integration for request/response validation using the same
validation library as the domain layer, and automatic OpenAPI docs at
`/docs` satisfying the API-documentation requirement directly rather than
via a bolted-on extension.

**Q37. What actually changed in Pydantic v2 that matters for this
project specifically?**
The validation core (`pydantic-core`) was rewritten in Rust — independent
benchmarks put v2 at roughly 4-50x faster than v1.9 depending on the
model shape, most noticeable on nested JSON. That matters here because
every request/response model, every agent tool argument, and the agent's
final structured output all go through that validation path on every
call — it's not an incidental detail, it's on the hot path for both the
REST and agent routes.

**Q38. How does `pydantic-settings` turn environment variables into
nested config objects?**
Via `__`-delimited env var names mapping to nested `BaseModel` fields —
`SECURITY__RATE_LIMIT_ENABLED` populates `Settings.security.rate_limit_enabled`.
Combined with `@lru_cache`-wrapped `get_settings()`, this gives one
validated, typed settings object built once per process and reused
everywhere, instead of scattered `os.environ.get()` calls with no
validation or type coercion.

**Q39. How does APScheduler's `AsyncIOScheduler` actually run an async
job function, and does that block anything?**
If the job function is a native coroutine (`async def`), `AsyncIOScheduler`
schedules it to run directly on the existing asyncio event loop — the
same loop FastAPI is already running requests on. A synchronous job
function instead runs in the event loop's default executor (a thread
pool). This project's batch job is a coroutine, so it shares the loop
rather than spinning up a separate thread — meaning a long-running batch
job and incoming API requests are cooperatively multitasked, not
isolated.

**Q40. What is `respx`, and why is it used instead of mocking
`WeatherService` methods directly in tests?**
`respx` intercepts httpx requests at the transport layer, so a test
registers a mock response for a specific URL/method and the *real*
`httpx.AsyncClient`, retry logic, and response-parsing code all still run
against it. Mocking `WeatherService.get_current_by_location_id` instead
would mean the test never exercises the actual HTTP client, retry, or
error-mapping logic — the whole point of testing at the protocol boundary
rather than the business-logic boundary.

**Q41. How does PydanticAI's `FunctionModel`/`TestModel` let the agent be
tested with zero live LLM calls?**
`FunctionModel` takes a plain Python function that inspects the message
history and returns a scripted response (text, a tool call, or a
structured final output) — PydanticAI treats it exactly like a real model
backend, so the *real* agent loop runs: tool dispatch, schema validation,
the retry-on-validation-failure path. It's the same instrumented/
protocol-boundary-faking approach as `respx` for HTTP, applied to the LLM
call itself.

**Q42. Why `uv` instead of pip/poetry/pipenv?**
`uv` (Astral, written in Rust) unifies dependency resolution, virtualenv
management, Python-version installation, and script execution
(`uv run`) into one tool with reported 10-100x faster installs than pip —
fewer moving parts in local dev, CI, and the Docker builder stage than
juggling separate lockfile/environment tools, and `uv sync --frozen`
against a committed `uv.lock` gives fully reproducible builds.

**Q43. Why Alembic for migrations instead of `Base.metadata.create_all()`
everywhere, given SQLite is single-writer anyway?**
`create_all()` only handles the "table doesn't exist yet" case — it can't
express an *incremental* schema change (adding a column, changing a
type) against a database that already has data. Alembic tracks a linear
migration history so schema evolution is repeatable and reviewable, the
same discipline a Postgres-backed version of this app would need,
practiced from day one even though SQLite's own DDL flexibility is more
limited.

**Q44. Why NiceGUI over Streamlit, and why was Gradio (the original
choice) replaced?**
The requirement was mounting the UI *in-process* into the existing
FastAPI app — no separate UI container. NiceGUI does this natively via
`ui.run_with(app, mount_path="/ui")`; Streamlit fundamentally can't, it
only runs as its own standalone server process. Gradio was the original
pick but was replaced after a reproducible frontend crash:
`functools.partial`-wrapping an async-generator callback broke Gradio's
internal dispatch, confirmed via a minimal reproduction with zero custom
code involved — not a bug in this project's code, a real limitation of
that Gradio version.

**Q45. What does `Agent.instrument_all()` actually add, mechanically?**
It wires PydanticAI's internal call sites (model requests, tool
invocations) to emit OpenTelemetry spans following the GenAI semantic
conventions — model name, token usage, tool name/arguments as span
attributes — so an agent run shows up in the same trace as the HTTP
request and any deterministic service calls it triggers, without a
separate LangSmith-style integration.

---

## Section 6 — Testing Strategy

**Q46. How do 115 tests run in under 30 seconds with zero network calls
or API keys?**
Every external dependency is faked at the *protocol* boundary, not the
business-logic boundary: Open-Meteo via `respx` (real HTTP client code
still runs), the LLM via PydanticAI's `FunctionModel` (real agent loop
still runs), Docker Compose config validated via `docker compose config`
with a CLI-availability skip if Docker isn't present. That's what keeps
the suite deterministic and fast while still exercising real retry logic,
real schema validation, and real provider-selection logic — not just
asserting mocks were called.

**Q47. Give a concrete example of a test that proves an architectural
guarantee, not just a code path.**
The test that breaks the agent module on purpose and asserts
`/v1/weather/current` still returns 200 — it doesn't test "the weather
endpoint works," it tests "the weather endpoint cannot be affected by the
agent," which is the actual claim being made about the architecture (Q4).
Similarly, a test asserting the mock Open-Meteo upstream is called
*exactly once* under concurrent requests for the same location proves
request coalescing, not just that caching exists.

**Q48. Why does the NiceGUI UI need a `mount_ui` flag on `create_app()`
just for tests?**
`nicegui.core.app` is a process-wide singleton; `ui.run_with()` builds a
middleware stack that can only be constructed once per process. Every
test building a fresh `create_app()` instance would hit "Cannot add
middleware after an application has started" on the second call. The flag
defaults the shared test fixture to `mount_ui=False`, with one dedicated
fixture (`app_client_with_ui`) as the only place in the whole suite that
mounts it — avoiding the singleton conflict by construction rather than
by test ordering discipline.

---

## Section 7 — Concurrency & Performance

**Q49. Explain request coalescing as implemented here, precisely.**
Concurrent requests for the same `location_id` within the cache TTL share
a single in-flight upstream call instead of each firing its own — the
first caller's request "wins" and later concurrent callers await the same
result rather than issuing redundant Open-Meteo calls. Verified by a test
asserting the mocked upstream is invoked exactly once under concurrent
load, not once-per-caller. Behind the standard "single-flight" pattern
implemented directly against `asyncio` primitives rather than a
third-party library, keeping the cache layer's dependency footprint
minimal.

**Q50. If this system were under real load and `sqlite_busy_errors_total`
started climbing, what's your actual diagnostic and response sequence?**
First, `DATABASE__BUSY_TIMEOUT_MS` — raising it buys time before treating
a `SQLITE_BUSY` as a real failure, since WAL mode allows one writer at a
time and momentary contention is expected under bursts. If the metric
keeps climbing after that, it's a signal the write load has genuinely
outgrown single-writer SQLite, not a config tuning problem — at that
point the response is the documented migration (Postgres via the
repository-layer swap, Q6), not further timeout tuning, because tuning a
timeout doesn't fix a throughput ceiling.

---

## Sources

Claims about third-party library internals (not this project's own code)
were verified against current documentation rather than asserted from
memory:

- [pydantic-core: Core validation logic for Pydantic written in Rust](https://github.com/pydantic/pydantic-core)
- [SQLAlchemy 2.0 — Asynchronous I/O (asyncio) extension, greenlet dependency](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [APScheduler — asyncio scheduler/executor, native coroutine job support](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html)
- [uv — Astral's Rust-based Python package and project manager](https://github.com/astral-sh/uv)
