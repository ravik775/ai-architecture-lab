# Security Hardening Plan - GenAI Observability Service

Status: **plan only, nothing in this document has been implemented yet.**
This is the research + design pass requested before writing any code.
Everything below is either a verified finding against this repo's actual
code (checked by reading the files, not assumed) or backed by a source
in the "Sources" section at the end.

---

## 1. Current-state audit (what this codebase actually does today)

Before designing defenses, it's worth being precise about what already
happens, because the honest answer changes the plan:

| Question | Finding |
|---|---|
| Do our own OTel spans (`app/observability/tracing.py`, `app/llm/chain.py`) ever attach raw user message or LLM response *content* as an attribute? | **No.** `chat.request` records `app.request.message_length` (an int), never the message itself. `litellm.completion` records model/temperature/token counts/cost/finish_reason - never `messages` or `choices[].message.content`. |
| Does `FastAPIInstrumentor.instrument_app(...)` (auto-instrumentation in `main.py`) capture request/response bodies? | **No** - this instrumentation captures method/route/status by default; header capture is opt-in via `http_capture_headers_server_request/response` (not set here), and it has no body-capture feature at all. |
| Does our Python `logging` output anywhere interpolate raw user message text? | **No** - checked every `logger.*` call in `main.py`, `app/api/routes.py`, `app/health/monitor.py`; all log service metadata, config booleans, or exception objects, never `payload.message` or `assistant_message`. |
| Do we register any litellm `success_callback`/`failure_callback` (e.g. litellm's built-in Langfuse integration, which *does* send full prompts/completions by default)? | **No** - `litellm.completion()` is called directly with no callbacks configured. |
| Does the Prometheus/OTel metrics pipeline (`app/observability/metrics.py`) use any user-controlled value as a metric label? | **No** - labels are `gen_ai.request.model`, `app.status`, `gen_ai.token.type`, `app.health.outcome` - all fixed-cardinality, app-controlled strings. |
| Does the Dockerfile run as a non-root user? | **No** - no `USER` directive, container runs as root. |
| Is there authentication on `POST /chat`? | **No** - documented as a known limitation in the main README, but worth restating here as an open item. |
| Is OTLP traffic (app -> collector -> Langfuse/LangSmith/Prometheus) encrypted? | **No** - plain HTTP inside the Docker bridge network; fine for single-host local dev, not fine the moment any of these hops cross a network boundary. |
| Are secrets (`OPENROUTER_API_KEY`, `LANGFUSE_SECRET_KEY`, etc.) stored anywhere other than `.env`? | No - `.env` is gitignored, which is correct, but it's still a plaintext file and the values land in each container's process environment (visible via `docker inspect` / `/proc/<pid>/environ` to anyone with host or container access). |

**The headline finding: there is currently no PII leak path in this
codebase's telemetry**, because message *content* is never captured
anywhere - not in spans, not in logs, not in metrics. That's a
deliberate byproduct of keeping the original build simple, not an
accident of good security design, and it has a real cost: you currently
can't see what a user actually asked or what the model answered in
Langfuse, which limits how useful the traces are for debugging real
issues.

**This changes the framing of the plan.** The risk here is *forward-looking*:
the moment anyone (including future you) does any one of the following,
a leak path opens up silently, because none of these are unusual or
wrong things to want to do:

- adds `gen_ai.prompt`/`gen_ai.completion`-style attributes to the
  `litellm.completion` span, to actually see conversations in Langfuse
  (a completely reasonable ask - "why can't I see what the user said" is
  the first thing anyone will ask after using this for a week);
- registers litellm's built-in Langfuse `success_callback`, which sends
  full request/response content by default;
- adds `opentelemetry-instrumentation-langchain` or similar
  community auto-instrumentation, which - unlike `FastAPIInstrumentor` -
  commonly captures prompt/completion content by default;
- logs `payload.message` or `result["assistant_message"]` at DEBUG level
  while chasing down a bug, and forgets to remove it.

So the plan below is about **building the guardrail before the capability
exists**, so that adding richer observability later is safe by default
instead of something that has to be remembered.

---

## 2. PII-in-telemetry design (the specific question asked)

### 2.1 Layered redaction - defense in depth, not one control

Industry practice (OpenTelemetry's own security guidance, Langfuse's
masking feature, litellm's Presidio guardrail) converges on the same
shape: **don't rely on a single point of redaction**, because any one
layer can be bypassed by a future code change nobody thought to check
against it. The plan is four independent layers; a leak has to get past
all of them, not just one:

**Layer 1 - App-level masking function (primary control).**
A `redact(text: str) -> str` utility in a new `app/observability/redaction.py`,
applied at the one and only place content would ever be attached to a
span/log: a helper like `set_llm_content_attributes(span, prompt=..., completion=...)`
that always redacts before calling `span.set_attribute`. This is the
Langfuse-recommended pattern (their SDK's `mask` parameter does exactly
this - runs a function over trace data before export) applied at our
own instrumentation boundary instead of vendor SDK boundary, so it works
regardless of which `OBSERVABILITY_PROVIDER` is active.

- Detection approach - this is the first open decision (see Section 5):
  regex-based (fast, zero new dependencies, catches structured PII:
  emails, phone numbers, credit cards, SSNs, API-key-shaped strings) vs.
  Microsoft Presidio (NER-based, catches unstructured PII like names and
  addresses that regex can't, but adds a real dependency + latency -
  litellm ships a native Presidio guardrail integration we could reuse
  instead of hand-rolling one).
- Field-level, not whole-text redaction: replace the matched substring
  (`ravik775@gmail.com` -> `[EMAIL]`) rather than dropping the whole
  message, so traces stay useful for debugging - this is the specific
  tradeoff Langfuse's own PII guidance calls out (aggressive whole-text
  scrubbing kills debuggability).

**Layer 2 - Collector-level redaction processor (defense in depth).**
Add the OTel Collector's `redaction` processor to
`collector/otel-collector-config.yaml`, in **allowlist mode**: only
explicitly allowed attribute keys pass through at all; anything else is
dropped, and configured value-regexes (email/phone/credit-card patterns)
are masked even on allowed keys. This is the safety net for the
scenario Layer 1 can't cover - a future third-party instrumentation
library (LangChain, litellm's own OTel hooks) that attaches content to
spans through a code path that never goes through our `redact()`
helper. Verified limitation: the redaction processor only supports
*traces* in allowlist mode; logs/metrics would need the `attributes`
processor with delete actions instead - relevant since our metrics
pipeline exists now too (Section 2.2 below is why this matters less
there).

**Layer 3 - litellm/Presidio guardrail (protects the input, not just
the telemetry).** Optional but worth calling out separately: litellm has
a first-class Presidio integration that can mask PII in the
request/response *before* it reaches OpenRouter and before it's written
to `app/llm/memory.py`. This is a different problem from telemetry
redaction - it protects what's stored in conversation memory and what
leaves your infrastructure to the model provider, not just what lands
in Langfuse. Worth having but scoped as a separate, later decision since
it changes application behavior (masked text is what the model sees),
not just observability.

**Layer 4 - Logging filter (safety net for logs specifically).** A
`logging.Filter` subclass registered on the root logger that runs the
same `redact()` function over the formatted log message before it's
emitted, so a future `logger.debug(f"user said: {message}")` added
during someone's late-night debugging session doesn't ship raw PII to
stdout/log aggregators even though it technically shouldn't have been
added in the first place.

### 2.2 Metrics-specific note

Metrics labels are a different risk shape than span attributes: a
high-cardinality or user-controlled label value (e.g. accidentally using
`session_id` or message text as a Prometheus label) is both a PII risk
*and* a cardinality/cost explosion risk in Prometheus, independent of
security. Current instruments are already safe (audited in Section 1),
but this is worth a standing rule as new metrics get added: **metric
label values must come from a fixed, small, app-controlled set
(model name, status enum, token type) - never from user input, ever**,
enforced by code review rather than a technical control, since Prometheus
has no equivalent of the redaction processor for this.

## 2.3 Cost & performance analysis (benchmarked, not estimated)

Answering "what does adding PII redaction actually cost" concretely,
per layer - measured where the sandbox environment allowed it, sourced
to published benchmarks where it didn't (Presidio requires downloading
a spaCy language model from GitHub Releases, which this environment's
network policy blocks - noted rather than glossed over).

### Layer 1/4 (regex) - measured directly

Benchmarked the exact pattern set from Section 2.1 (email, phone, credit
card, SSN, API-key-shaped, IPv4 - 6 compiled regexes applied
sequentially) against realistic message lengths, 20,000 iterations each,
single-threaded CPython on the machine running this analysis:

| Message length | Time per call | Calls/sec (single thread) |
|---|---|---|
| 100 chars | ~25 microseconds | ~40,600 |
| 500 chars | ~78 microseconds | ~12,900 |
| 2,000 chars | ~362 microseconds | ~2,760 |
| 4,000 chars (our `message` field's `max_length`, worst case) | ~800 microseconds | ~1,250 |

At the worst case (a maxed-out 4000-character message), regex
redaction costs **under 1 millisecond**. Against a typical OpenRouter
completion latency of hundreds of milliseconds to a few seconds, that's
well under 1% overhead even before considering where in the request
lifecycle it runs (next point).

**Where the cost lands is a real design choice, not a given.** Two ways
to wire Layer 1 in, with different latency implications:

- **Inline** (what Section 2.1 originally described): call `redact()`
  inside `set_llm_content_attributes()`, synchronously, while the span
  is still open in the request handler. This adds the ~1ms above
  directly to `/chat` response time - small, but not zero.
- **Deferred to the export thread** (better, verified against the SDK
  source in this session): wrap the configured `SpanExporter` (the
  object passed to `BatchSpanProcessor`, not a `SpanProcessor` - checked
  `BatchSpanProcessor.on_end()`, it only enqueues the span reference and
  returns immediately; the actual `exporter.export(batch)` call happens
  later, on the processor's own background thread) and run `redact()`
  inside that wrapper's `export()` method instead. Same ~1ms cost, but
  it's paid entirely on a background thread - **zero added `/chat`
  latency**, regardless of message length or traffic volume.

  The deferred approach is the one to build - it's a small change
  (redact in an `export()` override instead of at attribute-set time)
  for a real latency guarantee, consistent with how this service already
  treats span export as something that must never block the request
  (`docs/SECURITY-PLAN.md` Section 1 confirms `BatchSpanProcessor` is
  already async for exactly this reason).

### Layer 2 (Collector redaction processor) - already off the request path, cost is bounded by tail_sampling

This one was never in the request path to begin with (it runs in the
Collector container, not the app). Its real cost is Collector CPU,
proportional to *exported* span volume - and that volume is already
capped by the `tail_sampling` `rate_limiting` policy shipped in the
previous round. That's a genuine synergy worth noting: the load-based
sampling work already done bounds the marginal cost of adding Layer 2
later, for free.

### Layer 3 (litellm/Presidio guardrail) - the expensive one, and the only one that can't be deferred

Published, cross-referenced benchmarks (not measured live here - see
above): Presidio's analyzer costs roughly **10-25 milliseconds per
request** on typical hardware, of which **~95% is spaCy's NER model
inference**, not Presidio's own logic. Compared to the <1ms regex cost,
that's roughly **15-30x more expensive per call**.

Two costs beyond latency:
- **Dependency/image footprint**: `presidio-analyzer` itself is a few
  MB, but it requires a spaCy language model - `en_core_web_lg` (the
  more accurate option) is ~560MB; smaller models trade accuracy for a
  much lighter footprint. Either way, this is a meaningfully larger
  Docker image and a slower cold start (the model loads into memory
  once at process startup) than anything else in this service.
- **This layer cannot be deferred to a background thread**, unlike
  Layers 1/2/4. Its entire purpose is masking PII *before* it reaches
  OpenRouter and *before* it's written to `app/llm/memory.py` - it has
  to run inline, synchronously, in the request path, because it changes
  what actually gets sent. The 10-25ms is a real, unavoidable addition
  to `/chat` latency if this layer is built - still small relative to
  the LLM call itself, but an order of magnitude more than the other
  three layers combined.

### The asymmetry this creates

Layers 1/2/4 only protect *telemetry* (what ends up in Langfuse/logs).
None of them stop real PII from reaching OpenRouter or sitting in
`app/llm/memory.py` - only Layer 3 does that, and it's the one layer
that's both the most expensive and the one still deferred (Phase 3,
"only if a concrete need shows up in practice"). Worth being explicit
about the tradeoff being made by deferring it: cheap, fast, request-path-invisible
protection for the observability backend now; the actual
model-provider/memory exposure remains open until Layer 3 is built.

### Non-latency costs (all four layers)

- **False positives** (over-redaction) hurt debuggability - a regex
  that's too eager turns a legitimate order number into `[CREDIT_CARD]`
  and now you can't debug the thing you were trying to debug. This is
  an ongoing tuning cost, not a one-time build cost.
- **False negatives** (under-redaction) are the residual risk regex
  can't close - names, addresses, and other unstructured PII regex
  categorically can't catch. This is Presidio's actual value
  proposition, not just "more accurate" - it's a different *class* of
  detection (NER vs. pattern matching), which is also why it's slower.
- **Maintenance**: regex patterns need upkeep as new PII shapes show up
  in practice (non-US phone formats, new API key prefixes, etc.);
  Presidio needs model/version upkeep instead. Neither is a one-time
  cost.

---

## 3. Broader security features (the second half of the question)

Organized by layer, each with what's missing today and why it matters
for *this specific service* (an LLM-backed API with an observability
pipeline), not a generic checklist:

### AuthN / AuthZ
- `POST /chat` has zero authentication - anyone who can reach port 8000
  can spend your OpenRouter budget. Minimum viable fix: API key header
  auth with constant-time comparison (`secrets.compare_digest`), scoped
  per caller if you want per-key rate limits later.
- Health/metrics endpoints (`/health/*`) are lower risk (no cost, no
  data) but still shouldn't be internet-exposed without at least network
  restriction, since they reveal internal component names/success rates.

### Rate limiting & cost control
- No rate limiting exists anywhere. For an LLM endpoint this is a
  **cost** control as much as a security control - an unrated `/chat`
  is a direct line to unbounded OpenRouter spend. `slowapi` (Redis- or
  memory-backed) per API key or per IP is the standard FastAPI answer.

### Secrets management
- `.env` + Docker Compose env vars is the right *shape* for local dev,
  wrong for anything beyond it - env vars are visible to anything with
  container/host access. For a real deployment: Docker/Swarm secrets,
  or a vault (HashiCorp Vault, AWS/GCP secret manager), injected at
  runtime rather than baked into the environment.
- Key rotation: none of `OPENROUTER_API_KEY`, `LANGFUSE_SECRET_KEY`,
  `LANGSMITH_API_KEY` have any rotation story today - fine for a demo,
  a real gap for production.

### Transport security
- OTLP traffic (app -> collector, collector -> Langfuse/LangSmith/
  Prometheus) is plaintext HTTP. Inside a single Docker host's bridge
  network this is a reasonable simplification; the moment the collector
  and the app (or the collector and Prometheus) are on different hosts
  or in a shared cluster with other tenants, this needs TLS at minimum,
  mTLS if the collector should also authenticate *which* services are
  allowed to send it telemetry (verified: the Collector supports both
  server-mode and client-mode TLS, and mTLS via client-cert
  verification, natively).

### OWASP Top 10 for LLM Applications (2025) - relevance to this service
Verified current list: LLM01 Prompt Injection, LLM02 Sensitive
Information Disclosure, LLM03 Supply Chain, LLM04 Data/Model Poisoning,
LLM05 Improper Output Handling, LLM06 Excessive Agency, LLM07 System
Prompt Leakage, LLM08 Vector/Embedding Weaknesses, plus two further
categories in the 2025 list. Mapped to this repo specifically:

| Risk | Relevant here? | Notes |
|---|---|---|
| LLM01 Prompt Injection | Yes | User message goes straight into the LLM call with no input validation/sanitization. Low blast radius today (no tool-calling, no agency), but worth input-length/content checks regardless. |
| LLM02 Sensitive Info Disclosure | Yes | This is Section 2 above, plus: the model itself could echo back PII a user pastes in - masking at the telemetry layer doesn't stop that, only Layer 3 (Presidio-before-the-model) would. |
| LLM03 Supply Chain | Yes | `requirements.txt` pins exact versions (good baseline) but nothing scans for known CVEs in litellm/langchain/langgraph or their transitive deps. `pip-audit` or `trivy` in CI is the standard fix. |
| LLM05 Improper Output Handling | Yes | `result["assistant_message"]` is returned as JSON and would be caller's responsibility to render safely - worth documenting explicitly rather than assuming; if this ever gets a web frontend, treat LLM output as untrusted the same way you'd treat any user-generated content (escape before rendering as HTML). |
| LLM06 Excessive Agency | Not yet | No tool-calling/agentic behavior in the current graph - flagged for when `node.llm_generate` grows tool use. |
| LLM07 System Prompt Leakage | Low | `SYSTEM_PROMPT` in `chain.py` is generic/non-secret already - correct pattern, just confirming it stays that way (never put access-control logic or secrets in a system prompt). |

### Container / infrastructure hardening
- Add `USER` directive to `Dockerfile` (currently runs as root).
- Add resource limits (`mem_limit`/`cpus` or Compose `deploy.resources`)
  so a runaway process can't take down the host.
- Consider read-only root filesystem + explicit writable volumes only
  where needed (this service doesn't write to disk at all currently
  beyond Python's own bytecode cache, so this is a cheap win).

### Observability backend access control
- Once traces/metrics exist, they *are* a data store - anyone with
  Langfuse/LangSmith project access or a route to Prometheus `:9090`/
  collector `:8889` can see them. These ports are currently published
  to the host (`docker-compose.yml` `ports:`) for local convenience;
  in any shared or internet-facing environment they should not be
  publicly bound, and Langfuse/LangSmith project access should follow
  least-privilege team membership.

### Audit logging
- No record today of *who* called `/chat`, from where, how often. Once
  API-key auth exists (above), logging key-id + timestamp + outcome for
  every call is a natural addition and is also what makes per-key rate
  limiting and anomaly detection possible later.

---

## 4. Phased implementation plan

Ordered by risk-reduction-per-hour-of-work, not by how the topics were
listed above:

**Phase 1 - cheap, high-value, no new infrastructure**
1. `app/observability/redaction.py` - regex-based `redact()` covering
   email, phone, credit card, SSN-shaped, and API-key-shaped patterns.
2. Wire `redact()` into a new `set_llm_content_attributes()` helper -
   *not used yet* by default (content still isn't captured), but ready
   for the day someone wants prompt/completion visibility, so it's
   available and tested before it's needed.
3. Logging filter (Layer 4) registered in `main.py`'s logging setup.
4. `USER` directive in `Dockerfile` (run as non-root).
5. API key auth on `/chat` (header-based, constant-time compare).
6. Basic rate limiting on `/chat` (`slowapi`, in-memory backend is fine
   for a single-container demo).

**Phase 2 - moderate effort, real infrastructure changes**
7. OTel Collector `redaction` processor (Layer 2), allowlist-mode, in
   `collector/otel-collector-config.yaml`.
8. `pip-audit` (and optionally `trivy` for the image) wired into a CI
   step or at least documented as a pre-release check.
9. Stop publishing `otel-collector`'s `:8889` and `prometheus`'s `:9090`
   to the host by default in `docker-compose.yml` (bind to the internal
   network only; make host publishing opt-in via an override file for
   local debugging).

**Phase 3 - only if/when this leaves a single trusted host**
10. TLS between app <-> collector and collector <-> Prometheus/Langfuse
    egress (mTLS if the collector should authenticate callers).
11. Secrets manager integration in place of `.env`.
12. litellm Presidio guardrail (Layer 3) if there's an actual need to
    mask PII in what reaches OpenRouter, not just in telemetry.

---

## 5. Decisions needed before writing code

These are genuine tradeoffs, not implementation details I should
default silently - flagging them for you rather than picking for you:

1. **PII detection method for Layer 1**: regex-only (fast, zero new
   dependencies, matches the "keep it simple" spirit of the original
   build, but misses names/addresses/unstructured PII) vs. Presidio
   (catches more, adds a real dependency and per-call latency). A
   layered option also exists: regex now, Presidio as a Phase 3 addon.
2. **How far to take Phase 1 auth**: a single shared API key via env
   var (minimal, matches this repo's current simplicity) vs. per-caller
   keys with individual rate limits (more realistic for a real
   deployment, more to build/document).
3. **Which phase to implement first**: everything in Phase 1, or a
   narrower slice (e.g. just the redaction utility + logging filter,
   deferring auth/rate-limiting to a separate pass)?

---

## 6. Confirmed scope (pending one open question - see 6.4)

Reconciling your answers against Section 4's phased plan:

### 6.1 Layer 1 PII detection - confirmed: regex-only, pluggable

Build `redact()` as regex-based (email/phone/credit-card/SSN/API-key
patterns), but behind a small `PIIDetector` protocol/interface
(`detect(text) -> list[Match]`) so a `PresidioDetector` implementing the
same interface can be dropped in later (Phase 3, item 12) without
touching any call site. Nothing Presidio-specific ships now - no new
dependency, no latency cost - but the seam exists on day one instead of
being retrofitted.

### 6.2 Scope - confirmed: Phase 1 (all) + Phase 2 (all) + Phase 3 (items 10 and 12 only)

| Phase | Items | Status |
|---|---|---|
| Phase 1 | 1-6 (redaction utility, content-attribute helper, logging filter, non-root Dockerfile, API key auth, rate limiting) | **All confirmed** |
| Phase 2 | 7-9 (Collector redaction processor, dependency/image scanning, stop publishing internal ports by default) | **All confirmed** |
| Phase 3 | 10 (TLS/mTLS for collector egress), 12 (litellm Presidio guardrail) | **Confirmed** |
| Phase 3 | 11 (secrets manager integration) | **Explicitly excluded** from this pass |

### 6.3 New items added to scope this round (not in the original Section 4 list)

Raised in this session's follow-up questions - both are sampling-control
mechanisms, so they belong next to item 2 (`ParentBased(TraceIdRatioBased)`)
conceptually, slotted into Phase 1/2 since neither needs new
infrastructure:

13. **Load-aware sampling ratio** - today `TRACE_SAMPLING_RATIO` is a
    static number set once at startup. Add a feedback mechanism that
    adjusts the *effective* ratio based on recent request rate (a
    token-bucket/rate-limiting sampler wrapping `TraceIdRatioBased`, OR
    delegate this to the Collector's `tail_sampling` processor's
    `rate_limiting` policy, which already does exactly this
    server-side). See the chat response for the full explanation of
    both options and the tradeoff between them.
14. **Force-sample header** - an HTTP header (e.g. `X-Force-Trace: true`)
    that guarantees a specific request is captured at 100% fidelity
    regardless of the sampling ratio, implemented as a custom `Sampler`
    that checks OpenTelemetry `Baggage` (populated from the header by a
    small FastAPI middleware) before falling back to
    `ParentBased(TraceIdRatioBased(...))`. "Cannot be ignored" needs one
    caveat spelled out before this is built: see the chat response for
    why a purely client-supplied header can force sampling *in* safely,
    but cannot itself be trusted to force anything to bypass PII
    redaction (Layers 1/2/4 still run unconditionally regardless of this
    header - the two mechanisms are independent).

### 6.4 Open question - resolved

Confirmed: API-key auth is in scope, scoped to `POST/GET/DELETE /chat*`
only (`/health/*` stays open) - matches the reading proposed above.

## 7. Implementation log

What's actually shipped vs. the confirmed scope in Sections 6.1-6.3,
kept honest and current rather than aspirational - **README.md's
"Security" section is the source of truth for exact status per risk;
this log is the chronological record of what happened, in what order.**

**Round 2 (this revision) shipped a narrower, explicitly-requested
slice, not the full Section 6.2 table:**

- Item 13 (load-aware sampling) - **shipped**, via the Collector-side
  `tail_sampling` `rate_limiting` policy option (not the SDK-side
  token-bucket alternative) - see `collector/otel-collector-config.yaml`
  and README "Load-based sampling."
- Item 14 (force-sample header) - **shipped**, `X-Force-Trace` +
  `ForceTraceSampler` (`app/observability/sampling.py`), gated by RBAC.
- Phase 1 item 5 (API-key auth) - **shipped**, plus RBAC (a `force_trace`
  permission beyond the originally-scoped plain auth) to gate item 14 -
  see `app/security/auth.py`.
- Phase 3 item 10 (TLS/mTLS) - **shipped** as an opt-in overlay
  (`docker-compose.tls.yml` + `certs/generate-certs.sh`), covering
  app<->Collector and Collector<->Prometheus. Collector<->Langfuse/LangSmith
  needed no work (already TLS via `https://`).

**Round 3 (this pass) - basic LLM guardrails:**

- Phase 1 item 6 (request-level rate limiting on `/chat`) - **shipped**.
  Per-API-key token bucket, `app/security/rate_limit.py`, env-configurable
  via `RATE_LIMIT_REQUESTS_PER_MINUTE` (default 30/min), returns 429 +
  `Retry-After` when exhausted. This is a distinct budget from the
  Collector-side `tail_sampling` `rate_limiting` policy shipped earlier -
  that one protects trace-pipeline load, this one protects OpenRouter
  spend/DoS exposure (OWASP LLM10). Explicitly in-memory/single-replica;
  a shared (Redis-backed) limiter is needed before running >1 app
  replica, since each replica would otherwise enforce its own
  independent budget.
- Minimal LLM01 (Prompt Injection) input guardrail - **shipped**. A
  `field_validator` on `ChatRequest.message` rejects whitespace-only
  input (the existing `min_length=1` alone lets a single space through).
  This is *not* prompt-injection detection - no keyword denylist or
  content classifier was added, deliberately: that class of check is
  brittle and easily bypassed, and doing it properly is a much larger,
  model-behavior-dependent effort out of scope for this pass. Documented
  as "Partially in place" (not "In place") in the README OWASP table for
  that reason.

**Round 4 (this pass) - PII redaction Layers 1/2/4:**

- Phase 1 items 1-3 (`redact()` utility, content-attribute helper,
  logging filter) - **shipped**. `app/observability/redaction.py`:
  `RegexPIIDetector` (email/phone/credit-card/SSN/API-key-shaped/IPv4 -
  the same 6 pattern classes benchmarked in Section 2.3) behind the
  `PIIDetector` protocol confirmed in 6.1, `redact()` (field-level,
  `[ENTITY_TYPE]` placeholders), `PIIRedactionLogFilter` (Layer 4,
  registered on the root logger in `main.py`), and
  `set_llm_content_attributes()` (`app/observability/tracing.py`) - not
  called anywhere yet, ready for when content capture is actually needed.
  The Presidio seam is real, not aspirational: `PIIDetector` is a
  `typing.Protocol`, and `get_pii_detector()` is the single factory
  function a `PresidioDetector` would be wired into - no other file
  would need to change.
- Layer 1 shipped **broader** than Section 2.1 originally scoped it: not
  just the (still-unused) content helper, but a `RedactingSpanExporter`
  that redacts every string-valued attribute on every span, regardless
  of key. Reason for the change: `app.session_id` is user-suppliable
  with no format constraint (`app/api/routes.py::ChatRequest`), so a
  user could put an email or anything else in it as their own tracking
  convention - narrow, content-helper-only redaction would have missed
  that entirely. Verified end-to-end in this session (not just unit
  tests): a `/chat` call with an email embedded in `session_id` came out
  as `app.session_id: "[EMAIL]-session"` across all 6 spans in the trace.
  Deferred to the export thread exactly as Section 2.3 specified (wraps
  the `SpanExporter`, not a `SpanProcessor`) - zero added `/chat` latency
  for every network exporter; only CONSOLE mode (dev-only,
  `SimpleSpanProcessor`) pays it inline, and that cost is sub-millisecond.
- Phase 2 item 7 (Collector `redaction` processor / Layer 2) - **shipped**
  in both `collector/otel-collector-config.yaml` and the `.tls.yaml`
  variant (kept identical, asserted by test). Verified against the
  *pinned* image version's actual schema (`otel/opentelemetry-collector-contrib:0.110.0`),
  not current upstream docs, which already describe newer fields
  (`allowed_values`, `hash_function`, `url_sanitizer`, etc.) this
  pinned version doesn't have - shipping those would have silently done
  nothing or failed to start. Allowlist built from an audit of every
  `set_attribute()` call site in the codebase, plus the FastAPI
  auto-instrumentation's real attribute set (captured directly in this
  session, not assumed) - and deliberately excludes `http.target`/`http.url`
  (embed the resolved request path, which can contain a user-chosen
  `session_id`) and `net.peer.ip` (the caller's IP - PII under GDPR,
  no operational need for it here).
- Not shipped this round: Phase 1 item 4 (non-root Dockerfile user),
  Phase 2 items 8-9 (dependency scanning, opt-in host-port publishing),
  Phase 3 item 12 (litellm Presidio guardrail / Layer 3 - still deferred
  pending a concrete need), Phase 3 item 11 (secrets manager - still
  explicitly excluded).

---

## Sources

- [Handling sensitive data - OpenTelemetry](https://opentelemetry.io/docs/security/handling-sensitive-data/)
- [Redacting Sensitive Data in the OpenTelemetry Collector - Dash0](https://www.dash0.com/guides/scrubbing-sensitive-data-with-opentelemetry)
- [Mastering the OpenTelemetry Redaction Processor - Dash0](https://www.dash0.com/guides/opentelemetry-redaction-processor)
- [Collector configuration best practices - OpenTelemetry](https://opentelemetry.io/docs/security/config-best-practices/)
- [How to Set Up mTLS Between OpenTelemetry Collectors and Backends](https://oneuptime.com/blog/post/2026-02-06-setup-mtls-opentelemetry-collectors-backends/view)
- [Inside the LLM Call: GenAI Observability with OpenTelemetry - OpenTelemetry blog](https://opentelemetry.io/blog/2026/genai-observability/)
- [PII masking patterns for LLM applications - Langfuse](https://langfuse.com/resources/engineering/pii-masking-llm-applications)
- [Data Masking (self-hosted) - Langfuse](https://langfuse.com/self-hosting/security/data-masking)
- [Managing Personal Data - Langfuse](https://langfuse.com/security/manage-personal-data)
- [Presidio PII Masking with LiteLLM - Complete Tutorial](https://docs.litellm.ai/docs/tutorials/presidio_pii_masking)
- [PII, PHI Masking - Presidio - liteLLM docs](https://docs.litellm.ai/docs/proxy/guardrails/pii_masking_v2)
- [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/)
- [LLM02:2025 Sensitive Information Disclosure & Prevention - Indusface](https://www.indusface.com/learning/owasp-llm-sensitive-information-disclosure/)
- [API Security Best Practices for Production Applications](https://oneuptime.com/blog/post/2026-02-20-api-security-best-practices/view)
- [FastAPI Rate Limiting - Compile N Run](https://www.compilenrun.com/docs/framework/fastapi/fastapi-security/fastapi-rate-limiting/)
