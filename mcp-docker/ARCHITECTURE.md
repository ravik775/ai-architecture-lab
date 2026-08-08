# AI Research Assistant — Architecture & Audit Notes

## Purpose

This is Use Case 1 of a larger MCP-on-Docker exploration: a Spring Boot + Spring AI
service that answers a question by calling an LLM which, mid-conversation, invokes a
web-search tool exposed through a **Dockerized MCP Gateway**. The goal is narrow and
deliberate — prove that Docker's MCP Gateway can front a real MCP server and be
consumed cleanly from a JVM app, wearing just enough production dressing (JWT auth,
rate limiting, circuit breaker/bulkhead, distributed tracing, a real audit trail) to be
a credible enterprise starting point, not a toy and not a full production system.

Every cross-cutting concern that doesn't have a genuine job to do in *this* use case is
deferred on purpose, with the reason recorded below, so the scope is auditable rather
than assumed.

## TOGAF 10 alignment (lightweight)

This is a single-iteration slice, not a full ADM cycle — the mapping below exists so
the design can be traced back to a recognizable architecture domain, not as a
substitute for real Business/Data/Application/Technology architecture documents.

| Domain | This use case |
|---|---|
| **Business Architecture** | One capability: "answer a question, using live web search when needed, with a compliance-grade record of the interaction." Actors: an authenticated internal user, scoped to one tenant. |
| **Data Architecture** | Single system of record for this slice: `chat_audit_log` in Postgres (tenant_id, user_sub, question, answer_snippet, trace_id, timestamp). No other persistent state. |
| **Application Architecture** | One Spring Boot service. Chat orchestration (Spring AI `ChatClient`), resilience (Resilience4j), authN/authZ (Spring Security OAuth2 Resource Server), audit persistence (Spring Data JPA + Flyway). |
| **Technology Architecture** | Five containers via Docker Compose: the app, Docker MCP Gateway (fronting a catalog MCP server), Keycloak, Postgres, Jaeger. |

## Request flow

```
Client --POST /api/chat (Bearer JWT)--> Spring Boot app
  1. Spring Security validates JWT (issuer = Keycloak realm), maps realm_access.roles
     to authorities, requires ROLE_user
  2. tenant_id extracted from a custom JWT claim (Keycloak protocol mapper)
  3. ResearchAssistantService.answer(...) — ONE method wrapped with
     @RateLimiter -> @Bulkhead -> @CircuitBreaker -> @TimeLimiter (Resilience4j)
  4. Spring AI ChatClient calls the OpenRouter-hosted model (qwen/qwen3-coder:free)
     with MCP tool callbacks registered
  5. Model decides it needs a search -> Spring AI's MCP client calls the Docker MCP
     Gateway over SSE (http://mcp-gateway:8811)
  6. Gateway routes to the containerized DuckDuckGo MCP server, returns results
  7. Model composes the final answer
  8. Answer persisted to chat_audit_log, tagged with tenant_id and the current
     OpenTelemetry trace_id
  9. One continuous trace (steps 3-8) exported via OTLP to Jaeger
<-- 200 { "answer": "..." }
```

`GET /api/audit` returns the caller's own tenant's rows only — row-level tenant
isolation, enforced by filtering on the `tenant_id` claim from the validated JWT.

## Verified component versions

Sourced and cross-checked during design (Aug 2026); flagged where confidence is lower.

| Component | Version / image |
|---|---|
| Spring Boot | 3.5.16 |
| Spring AI | 1.1.8 |
| Java | 21 (LTS) |
| Resilience4j | `resilience4j-spring-boot3` 2.2.0 |
| Docker MCP Gateway | `docker/mcp-gateway:v2` |
| Keycloak | `quay.io/keycloak/keycloak:26.7.0` |
| Postgres | `postgres:18-alpine` |
| Jaeger all-in-one | `jaegertracing/all-in-one:latest` — **not pinned to a patch tag.** Docker Hub's tag API returned only stale 2017-era data when queried from this environment; rather than invent a version number, this stays on `latest` with an explicit note to pin it (`docker image inspect` after first pull) before treating the stack as reproducible. |
| LLM | OpenRouter, `qwen/qwen3-coder:free` (swap via `OPENROUTER_MODEL` env var) |

## Design decisions and why

**One resilience boundary, not one per hop.** Spring AI's `ChatClient.tools(...).call()`
runs its tool-execution loop internally — there's no clean seam to wrap only the MCP
call without reimplementing that loop. `ResearchAssistantService.answer()` wraps the
whole LLM+tool exchange with `@RateLimiter` → `@Bulkhead` → `@CircuitBreaker` →
`@TimeLimiter`, using Resilience4j's **default aspect ordering** — no custom ordering
was configured. That default nests them as CircuitBreaker(RateLimiter(TimeLimiter(
Bulkhead(call)))) — CircuitBreaker is outermost, confirmed empirically (not just read
in docs): once the OpenRouter key was still a placeholder and every call failed, the
breaker opened around the 9th–10th call and every request after that returned `503`
immediately, including ones that a standalone rate-limiter check would've allowed —
i.e. once the breaker is open, it preempts the rate limiter rather than the other way
around. Worth knowing before assuming "rate limit hit" from a `503` — check the error
`code` in the response body (`rate_limit_exceeded` vs `downstream_unavailable`) to tell
them apart. This ordering is fine for this demo; tuning it is a scale concern.

Rather than four near-duplicate `fallbackMethod`s, the four exception types
(`RequestNotPermitted`, `BulkheadFullException`, `CallNotPermittedException`,
`TimeoutException`) propagate through the returned `CompletableFuture` and are mapped
to HTTP status codes in one place: `GlobalExceptionHandler`. That's a `429`, `503`,
`503`, and `504` respectively — a caller can tell "back off" apart from "try again
later" apart from "your request took too long."

| Setting | Value | Why |
|---|---|---|
| Rate limiter | 10 req / 60s | OpenRouter's free-tier cap is 20 req/min; staying at half that leaves headroom instead of silently burning the whole quota. |
| Bulkhead | 5 concurrent | Bounds how many slow LLM/tool round-trips can pile up before failing fast. |
| Circuit breaker | 50% failure rate / 10-call window, 10s open, 3 half-open probes | Standard conservative defaults for a low-volume service. |
| Time limiter | 15s | The whole exchange (LLM + any tool round-trip) should resolve well within this; if not, fail fast rather than hold the HTTP thread. |

**JWT/RBAC kept intentionally minimal.** One Keycloak realm, one client, two realm
roles (`user`, `admin`). `tenant_id` is a real user attribute mapped to a token claim —
not a hardcoded value — so tenant isolation on `/api/audit` is actually demonstrable
with two demo users (`alice`/tenant `acme`, `bob`/tenant `globex`).

- **CSRF is disabled**, deliberately: this is a stateless bearer-token API with no
  cookies or server-side session, and CSRF's threat model doesn't apply without one.
- **Token acquisition for this demo uses the Resource Owner Password Credentials
  grant** (`curl` with a username/password directly against Keycloak) because there is
  no browser-based client in this slice. This is **not** how a real client should
  authenticate — that would be Authorization Code + PKCE from an actual frontend. It's
  a test-harness convenience and is called out as such, not a production pattern.
- The demo client is a **public client** (no client secret) since it only exists to let
  a curl script obtain a token for testing; a real backend-to-backend client would be
  confidential. Documented rather than silently chosen.
- Keycloak realm-export.json ships with **plaintext demo passwords** for three
  throwaway accounts. This is standard for a dev-mode Keycloak realm import and every
  account only exists inside your local Docker network — but it is explicitly not a
  pattern to copy into anything that isn't a disposable local demo.

**Keycloak + Docker hostname gotcha, handled up front.** A JWT's `iss` claim has to
match the URL the resource server uses for both issuer validation and JWKS discovery.
Keycloak is configured with `KC_HOSTNAME=host.docker.internal`, published on host port
`8081`; the Spring app's `issuer-uri` points at that same address, which Docker Desktop
resolves from inside the app container automatically. `extra_hosts:
host.docker.internal:host-gateway` is included on both the `keycloak` and `app`
services so the same trick also works unmodified on Linux Docker Engine, where that
hostname isn't automatic.

**Postgres has one real job**: `chat_audit_log`. This isn't decorative — logging AI
interactions for compliance is a realistic requirement, and it's what makes tenant
isolation and trace correlation (`trace_id` column ↔ Jaeger) checkable instead of
merely asserted. Schema is Flyway-managed (`V1__create_chat_audit_log.sql`), not
`ddl-auto` — an audit table's schema shouldn't be silently auto-migrated.

**Observability stays to one container.** `micrometer-tracing-bridge-otel` +
OTLP export to a single Jaeger all-in-one — full waterfall trace across HTTP → resilience
wrapper → MCP tool call → LLM call, without standing up Tempo/Loki/Prometheus/Grafana
for a single-service demo. `management.tracing.sampling.probability=1.0` (trace
everything) is a demo setting, explicitly not what you'd run at production volume.

## Explicitly deferred (not silently dropped)

- **A separate API Gateway service** — nothing to route between with one backend.
  Spring Security + Resilience4j on the app *is* the edge today. Revisit once a second
  backend service exists.
- **Event-driven messaging (Kafka/RabbitMQ)** — this use case is synchronous
  request/response; there is no genuine async workflow yet to justify a broker. It
  belongs in a follow-on ticket-triage use case, not bolted on here for its own sake.
- **Full multi-tenant data isolation** (separate schemas/DBs per tenant) — a
  `tenant_id` column with row-level filtering proves the pattern at this scale;
  physical isolation is a scale/compliance decision for later.
- **Dependency/SBOM scanning** (e.g. OWASP dependency-check) — a real gap for a
  production audit, but adding the Maven plugin is a one-line follow-up, not core to
  proving the MCP pattern. Noted here rather than silently skipped.
- **Automated tests** — not included in this slice given the scope agreed (prove the
  MCP pattern end-to-end); flagged as the next thing to add before this graduates past
  a demo.

## Issues found while actually running the stack (not just designed on paper)

- **Postgres 18's image changed its expected volume mount point.** Mounting the named
  volume at `/var/lib/postgresql/data` (the long-standing convention) makes the
  container refuse to start — Postgres 18+ manages a version-specific subdirectory
  itself and expects the volume mounted one level up, at `/var/lib/postgresql`. Fixed
  in `docker-compose.yml`. Caught by actually running `docker compose up`, not by
  reading documentation in advance.

- **The `duckduckgo` MCP server no longer exists in Docker's live default catalog.**
  The design was based on Docker's own published `compose-for-agents/spring-ai`
  reference example, which uses `--servers=duckduckgo`. Running that against the
  actual current catalog (`https://desktop.docker.com/mcp/catalog/v3/catalog.yaml`)
  produced `0 tools listed` — the entry simply isn't there anymore; catalog contents
  have drifted since that reference was published. I fetched and read the live
  catalog directly rather than guess a replacement name. Of the ~100 servers
  currently listed, the only one offering general live web access **without a paid
  API key** is `curl` (a sandboxed container that runs literal curl commands) — every
  search-oriented option found (`brightdata`, etc.) requires a paid API token as a
  secret. Switched to `--servers=curl`. This changes the demo's tool from "search" to
  "fetch a specific URL," which is a real capability reduction worth naming plainly:
  the model needs a URL to act on, not just a topic. A production system would use a
  properly scoped fetch allow-list or a paid search API with its own governance, not
  an open curl passthrough — noted as a follow-up, not fixed here, to avoid adding a
  paid dependency to what's meant to be a free-to-run demo.

- **The MCP Gateway requires a Bearer token that Spring AI's SSE client cannot yet
  send.** By default the gateway generates a random per-run token (visible only in its
  own container logs) and rejects unauthenticated SSE connections — a real protection
  against DNS-rebinding attacks on a localhost-bound gateway. Spring AI's SSE MCP
  client has no supported way to attach a custom `Authorization` header per
  connection; this is a confirmed, open upstream gap
  ([spring-projects/spring-ai#4305](https://github.com/spring-projects/spring-ai/issues/4305)),
  not a missing config property I overlooked. Given that gap, the gateway now runs
  with `--allow-unauthenticated`, and its port is no longer published to the host —
  only the `app` container can reach it, over the internal Compose network. That's a
  real, accepted trade-off for this environment, not a silent one: it's fine here
  because the gateway has no route in from outside Compose, but it's the first thing
  to revisit if this ever moves beyond a local demo (either by pinning
  `MCP_GATEWAY_AUTH_TOKEN` and writing a custom transport/header-injecting bean once
  Spring AI supports it, or by fronting the whole app with a real network boundary).

- **`ChatClient` request spec: `.tools()` vs `.toolCallbacks()` on Spring AI 1.1.8.** A
  Spring AI reference page I fetched during design showed `.tools(toolCallbacks)`
  accepting a raw `ToolCallback[]`. Running against the actual pinned version
  (1.1.8) threw `IllegalStateException: No @Tool annotated methods found ... Did you
  mean to pass a ToolCallback or ToolCallbackProvider? If so, you have to use
  .toolCallbacks() instead of .tool()` — `.tools(Object...)` treats its argument as
  `@Tool`-annotated POJOs, not raw callbacks; the MCP-produced `ToolCallback[]` needs
  the separate `.toolCallbacks(...)` method. Fixed in
  `ResearchAssistantService.answer()`. The lesson generalizes: a fetched doc snippet is
  a claim about behavior, not a guarantee for the exact pinned version — this only got
  caught because the stack was actually run end-to-end, not just wired up on paper.

## Points I could not fully verify and flagged rather than guessed

- **MCP SSE endpoint path**: Spring AI's SSE client defaults to `/sse`; Docker's MCP
  Gateway `--transport=sse` is expected to match, based on Docker's own published
  `compose-for-agents/spring-ai` reference example, but I could not independently
  confirm the gateway's exact route from source in this environment. Verify against
  the gateway container's logs on first run.
- **Jaeger image tag**, as noted above.

## Running it

```bash
cp .env.example .env   # fill in OPENROUTER_API_KEY and set real passwords
docker compose up --build -d
```

1. Wait for all containers to report healthy: `docker compose ps`.
2. Get a token for `alice` (tenant `acme`):
   ```bash
   curl -s -X POST http://localhost:8081/realms/mcp-demo/protocol/openid-connect/token \
     -d client_id=research-assistant-app -d grant_type=password \
     -d username=alice -d password=alice-pw | jq -r .access_token
   ```
3. Ask a question that needs a live search:
   ```bash
   curl -s -X POST http://localhost:8080/api/chat \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"question":"What is the latest stable Spring Boot version?"}'
   ```
4. Open Jaeger at `http://localhost:16686` and find the trace — confirm it spans the
   HTTP request, the resilience wrapper, the MCP tool call, and the OpenRouter call.
5. Fire 11 requests in under a minute; the 11th should return `429 rate_limit_exceeded`.
6. `docker compose stop mcp-gateway`, then call `/api/chat` again — it should fail fast
   with `503 downstream_unavailable` once the circuit opens, instead of hanging ~15s
   per call.
7. `GET /api/audit` as `alice` and as `bob` (repeat step 2 with `bob`/`bob-pw`) —
   confirm each only sees their own tenant's rows.

### What's actually been verified vs. what still needs your OpenRouter key

Everything above the LLM call itself has been run end-to-end against the live stack,
not just designed on paper: container health, the Postgres 18 volume fix, Flyway
migration, JWT issuance and validation (issuer/JWKS resolution via
`host.docker.internal`), the `tenant_id` and realm-role claims decoding correctly, the
MCP handshake with the gateway (`Docker AI MCP Gateway v2.0.1`, 1 tool discovered), and
the request reaching OpenRouter with the correct URL shape (confirmed by getting back a
real OpenRouter JSON error, not a 404 routing failure). Firing 11 requests back-to-back
with a placeholder key also confirmed the circuit breaker: it opened after the
9th–10th failing call and started returning `503 downstream_unavailable` immediately
instead of continuing to hit OpenRouter — see the aspect-ordering note above.

What's **not yet verified** because it needs a real `OPENROUTER_API_KEY`: an actual
model response, the `curl` MCP tool being invoked mid-conversation, an audit row
actually being written, and rate-limiting in isolation (the circuit breaker trips first
when every call fails, so a clean 429 needs calls that succeed). Add a real key to
`.env` and run `docker compose up -d --build app` to complete those checks.
