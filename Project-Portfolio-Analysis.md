# Project Portfolio Analysis

**Author:** Ravi K
**Scope:** `ai-agent-gateway`, `ai-architecture-assistant`, `expense-ai`, `genai-observability`, `intellij-mcp-langgraph-assistant`, `pydanticai`
**Excluded from this audit:** `loan-processing-architecture`, `gemini-agent`
**Method:** Every claim below was checked directly against source code and `git log` on the `main` branch — not taken from each project's own README. Where a project's README overstates what the code does, that gap is called out explicitly, because it's exactly the kind of thing an interviewer (or a careful ATS/recruiter reading the repo) will find.
**Purpose:** identify what each project genuinely proves for an **AI Architect / Solution Architect** search, what's weak enough to hurt you if probed, a concrete plan to close each gap, and which project(s) belong on the resume.

---

## 1. `pydanticai` — Weather Intelligence Agent

**One-line:** A hexagonal-architecture weather service pairing a PydanticAI natural-language agent with a deterministic REST API, full dual-pipeline OpenTelemetry observability, and a 23-question "Solution Architect FAQ" defending every design decision.

### Strong points
- **Textbook layered/hexagonal design**: `domain/` (framework-free models + `Protocol` interfaces) → `application/` (services) → `infrastructure/` (SQLAlchemy, Open-Meteo HTTP, cache) → `agent/` → `api/`. Swapping the cache or weather provider is additive, not a domain rewrite — `WeatherProvider`/`WeatherCache` Protocols make this verifiable, not just claimed.
- **Real agent framework usage**: PydanticAI `Agent` with a `FallbackModel`, enforced `output_type=AgentQueryResult` structured output, six typed tools, and a system-prompt + structural design that makes the agent unable to fabricate data (`AgentDeps` only exposes application services, never the DB directly — backed by `test_agent_reports_provider_unavailable_without_fabricating`).
- **Deterministic agent testing**: PydanticAI's `FunctionModel`/`TestModel` exercise the real agent loop (retries, schema validation, tool dispatch, latency budgets) with zero live LLM calls — a genuinely sophisticated testing pattern most portfolio projects skip entirely.
- **Best observability in the portfolio for a single agent service**: full OTel trace pipeline (OTLP → Collector → Tempo), a custom rate-limited `Sampler` with an RBAC-gated force-trace override via W3C baggage, Prometheus metrics on an isolated port, structured JSON logs correlated by trace/span/request ID, Grafana dashboards checked into the repo.
- **Production Docker hygiene**: multi-stage build, non-root user, pinned base image, `HEALTHCHECK`, correct exec-form entrypoint for SIGTERM handling — details most reference projects get wrong.
- **106 tests** (unit + integration), all external I/O mocked at the protocol boundary — runnable with zero API keys.
- **Exceptional documentation**: a 597-line README including a self-written 23-question Solution Architect FAQ that pre-answers the trade-off questions an interviewer would ask.

### Weak points
- **Zero git history.** `git status` shows the entire folder as untracked (`?? pydanticai/`) — despite being the most substantial project in the portfolio, there is currently no commit narrative a reviewer could look at.
- **No CI/CD** — tests/lint/Docker build are all manual.
- **`/v1/*` business endpoints are unauthenticated** — only the `force_trace` override is RBAC-gated. Disclosed in the README, but still a real gap if pitched as more than a demo.
- **Single-replica architecture throughout** (in-memory cache, in-process scheduler, in-memory rate limiter, SQLite) — the scale-out path is documented but not implemented.
- **README self-inconsistency**: states "61 tests" in one place and "100+-test suite" in the FAQ; actual count is 106 — a careless reviewer-facing detail.
- **Demo-grade crypto** (PBKDF2, not bcrypt/argon2; single non-rotating JWT secret) — explicitly disclosed, but worth fixing before a portfolio push.
- Stray empty directory (`litellm_config.yaml;C`) in the repo root — cosmetic, but sloppy for a flagship project.

### Plan to close the gaps
1. **Commit it.** `git add pydanticai && git commit` — this is the single highest-leverage fix in the entire portfolio; an uncommitted flagship project undermines the "I actually build and ship this" narrative.
2. Fix the "61 tests" vs "106 tests" README inconsistency (one-line edit).
3. Add a minimal GitHub Actions workflow: `uv sync`, `ruff check`, `pytest` — turns "tests exist" into "tests are enforced," a common interview follow-up.
4. Add lightweight auth (even a shared API key) to `/v1/*` routes, or explicitly re-label them "demo-open by design" in the README's production-readiness checklist so it reads as a decision, not an oversight.
5. Swap PBKDF2 for `bcrypt`/`argon2` — a small dependency add, removes a "would you actually ship this?" objection.

### Positioning note
Lead with this project as the **architecture-depth** flagship: hexagonal layering, deterministic agent testing, and the dual-pipeline observability story are the strongest, most defensible technical claims in the portfolio — but only after it's committed to git. Don't claim "production" without listing the FAQ's own honestly-disclosed gaps if asked.

---

## 2. `expense-ai` — Agentic Expense Approval Platform

**One-line:** A LangGraph-orchestrated expense-approval workflow with durable PostgreSQL checkpointing for human-in-the-loop review, wrapped in a composable resilience-policy pipeline (retry, circuit breaker, cache, timeout, guardrails).

### Strong points
- **Real agentic orchestration**: a `StateGraph` (`app/agents/expense_approval_graph.py`) with conditional routing and `interrupt()`/`Command(resume=...)` — a legitimate, correctly-implemented durable human-in-the-loop pattern, not a toy graph. `PostgresSaver` checkpointing means an approval survives a process restart.
- **Composable resilience pipeline**: 9-step policy chain (`observability → provider_selection → retrieval → prompt_preparation → guardrail → cache → retry → circuit_breaker → timeout`), each policy an independently testable single-purpose file under `app/ai/policies/`. This is a clean, reusable architecture pattern, not scattered try/except blocks.
- **Genuine provider abstraction** via LiteLLM behind an `LLMService` interface, with a `MockLLMService` for testing — domain code depends only on the interface.
- **RAG wired end-to-end**: ChromaDB-backed policy retrieval, deterministic corpus seeding, integrated as a pipeline policy.
- **Structured output**: LLM responses validated into Pydantic `ExpenseAnalysis`/`ExpenseResponse` models.
- **Cost/token tracking + OpenTelemetry + LangSmith integration**, non-root Docker, two operating modes (basic vs. agentic) toggled by config — a nice, demonstrable architecture decision.
- **57 tests**, ~0.63:1 test-to-app-code ratio, and a clean 14-commit incremental history (Jul 25 – Aug 4) whose messages map directly to the README's own "module completion status" table — real, legible evidence of staged, deliberate engineering.

### Weak points
- **No authentication on any endpoint.** `passlib`/`python-jose` are listed as dependencies but never wired into any route — anyone reaching the port can submit or approve expenses.
- **RAG uses a fake embedding function.** `LocalHashEmbeddingFunction` (`app/rag/chroma_retriever.py`) is an MD5 hash-based bag-of-words vectorizer, not a real semantic embedding model — this is token-overlap matching dressed as vector search, and a reviewer who opens the file will see it immediately.
- **No CI/CD**, no lint config (no ruff/mypy).
- Leftover debug artifacts committed: `# FIX 1:`, `# FIX 2:`, `# FIX 3:` comments and a commented-out `print()` in `expense_approval_graph.py`.
- `logging.basicConfig(level=logging.DEBUG, force=True)` hardcoded in `main.py` rather than environment-driven.
- `Notes.txt` (raw scratch file) and a 223KB `repomix-output.xml` dump committed to the repo root — repo-hygiene noise for a "portfolio-ready" project.

### Plan to close the gaps
1. **Add authentication** — even a simple API-key dependency on the FastAPI routes closes the single biggest credibility gap; `passlib`/`python-jose` are already dependencies, so this is mostly wiring, not new tech.
2. **Replace the hash embedding with a real one** — swap `LocalHashEmbeddingFunction` for `sentence-transformers` (local, free) or an OpenAI/LiteLLM embeddings call. This single change upgrades "RAG plumbing demo" to "real semantic retrieval," which materially changes what you can honestly claim in an interview.
3. Delete `Notes.txt` and `repomix-output.xml` from the repo, or move them to a `docs/scratch/`-style gitignored path.
4. Remove the `# FIX N` comments and the dead `print()`; make `DEBUG` logging config-driven (`settings.log_level`).
5. Add a GitHub Actions workflow running `pytest` — the test suite already exists, it just isn't enforced.

### Positioning note
This is your strongest **agentic-workflow-with-durable-state** story — lead with the LangGraph interrupt/resume + Postgres checkpointing pattern, since durable human-in-the-loop design is exactly what "AI Architect" job descriptions ask about. Don't describe the RAG as "semantic search" until the embedding function is replaced — say "policy-retrieval pipeline" instead, which is accurate today.

---

## 3. `genai-observability` — GenAI Observability Reference Service

**One-line:** A deliberately minimal chat service whose entire purpose is demonstrating a production-shaped LLM observability stack: dual OTel pipelines, head+tail sampling, vendor-agnostic export, 4-layer PII redaction, and a documented OWASP LLM Top 10 self-assessment.

### Strong points
- **The deepest observability implementation in the portfolio.** Two independent OTel pipelines (traces vs. metrics, because Langfuse/LangSmith don't ingest OTLP metrics), a correctly-reasoned head-based (SDK ratio sampler) + tail-based (Collector-side "always keep errors") sampling split, and a custom `ForceTraceSampler` using OTel `Baggage` gated behind RBAC — genuinely nontrivial SDK extension work, not boilerplate.
- **Vendor-agnostic export by construction**: application code only ever imports the standard `opentelemetry` API; Langfuse/LangSmith SDKs are never imported in the default path — swapping backends is a config change (`OBSERVABILITY_PROVIDER=collector|langfuse_direct|langsmith_direct|console`).
- **4-layer defense-in-depth PII redaction** (span exporter wrapper, Collector processor, log filter — with the 4th layer, "what's actually sent to the LLM," explicitly and honestly marked as not-yet-built rather than glossed over).
- **Real security posture**: API-key + RBAC auth, constant-time comparison, per-key token-bucket rate limiting (OWASP LLM10), input validation.
- **A documented risk register and OWASP LLM Top 10 self-assessment** (`docs/SECURITY-PLAN.md` + README table) mapped to actual shipped files — this is unusually rigorous for a portfolio project and a genuine differentiator: it shows security *judgment*, not just a features list.
- **112 tests**, ruff-clean, correctly uses OTel GenAI semantic conventions (`gen_ai.system`, `gen_ai.usage.*`) — a concrete signal of real familiarity with the spec.

### Weak points
- **Currently untracked in git at its real location.** The folder was moved from `observability/genai-observability/` to the top-level `genai-observability/` and git sees it as new content; only 2 stale commits exist at the old path (`2604d2b`, `f2d051d`, Aug 5–6). A clone today would show this as entirely uncommitted.
- **Container runs as root** — no `USER` directive in the Dockerfile.
- **No retry/circuit-breaker around the LLM call** — a single OpenRouter failure just fails the request outright; self-documented as a known limitation, but a real gap next to `expense-ai`'s resilience pipeline.
- **In-memory-only rate limiter and session store** — doesn't survive multi-replica deployment or process restart (documented, not hidden).
- Regex-only PII detection — can't catch unstructured PII (names, addresses); Presidio is noted as a future swap, not built.
- No CI/CD; internal ports published to host by default (flagged in its own risk register).

### Plan to close the gaps
1. **Commit the current folder at its new path** — `git add genai-observability && git commit` (and confirm the old `observability/genai-observability` path is cleanly removed/rename-tracked so history isn't confusing).
2. Add `USER appuser` to the Dockerfile — a two-line fix that removes a real "would you actually run this" objection.
3. Add Tenacity retry (bounded, exponential backoff) around the LiteLLM/OpenRouter call — reuse the pattern already proven in `expense-ai`.
4. Add a GitHub Actions workflow (`ruff check` + `pytest`) — the project is already ruff-clean and has 112 tests, so this is close to a checkbox fix.
5. Consider Redis for the rate limiter/session store if you want to claim multi-replica readiness; otherwise keep the current "single-replica by design" framing, which is already honest.

### Positioning note
This is your strongest **observability-and-security-architecture** story — lead with the dual-pipeline design, the sampling strategy, and the OWASP self-assessment; that combination (a documented risk register mapped to code) is rare in portfolio projects and reads as genuine security maturity. Fix the git-tracking and root-container issues before showing the repo, since both are one-line fixes that currently undercut an otherwise excellent artifact.

---

## 4. `ai-agent-gateway` — Production-Style AI Agent Gateway

**One-line:** A small FastAPI agent gateway routing questions to a weather/calculator/web-search tool or a general LLM completion via LiteLLM — currently **broken as committed**.

### Strong points
- Clean small layering (`api → services → tools`) and a genuinely good security choice: the calculator tool uses an AST-based safe evaluator instead of `eval()`.
- Real LLM provider abstraction via LiteLLM with a fallback-model retry path (`tenacity`).
- A more sophisticated hybrid rule+LLM intent router exists (`intent_router.py`, confidence-scored, async) showing awareness of a better design than the one actually wired in.

### Weak points
- **The application cannot start.** `app/services/agent_service.py` has a module-level indentation error (every line indented 4 spaces from column 0) — `uvicorn app.main:app` crashes on import. This is the single most damaging finding in the portfolio: it's the first thing anyone following the README's own instructions would hit.
- **Even if the syntax were fixed, the wiring is logically broken**: `agent_service.py` imports the old, unused `intent_router_o.py` (whose `classify()` returns a plain enum) but calls it as if it were the newer async `intent_router.py` (which returns a `RoutingDecision` object) — attribute errors would follow immediately.
- The better hybrid router is **orphaned dead code** — never imported by the running app, and the existing tests cover the old router, not it.
- Only 4 tests, none exercising the API endpoints or the (broken) agent service.
- No Docker, no CI, no observability, no auth — all explicitly deferred per the README, which is honest, but combined with the broken import this project currently proves less than it claims.
- Single git commit, oddly labeled ("Removed Docker compose port" for what was actually the entire initial add) — no evidence of iterative fixes, including never fixing the broken file.

### Plan to close the gaps
1. **Fix the indentation error** in `agent_service.py` — trivial mechanically, but it's the blocker for everything else.
2. **Rewire to the better router**: replace the `intent_router_o` import with `intent_router.IntentRouter`, update the attribute access to match `RoutingDecision`, and delete `intent_router_o.py` once nothing references it.
3. Move the existing router tests onto the now-active hybrid router; add endpoint-level tests (`TestClient` hitting `/agent/ask`) so a broken import can never ship silently again.
4. Add a Dockerfile and a minimal CI workflow that at minimum runs `python -c "import app.main"` — would have caught this exact bug.
5. Once fixed, this becomes a legitimate, small "provider abstraction + tool-routing agent" demo — worth keeping as a secondary project, not a flagship.

### Positioning note
**Do not show this repo before fixing the import bug** — an interviewer who clones it and runs the README's own `uvicorn` command will see a crash in under a minute. After the fix (roughly an hour of work), it's a reasonable secondary example of LLM provider abstraction and tool-calling, but not strong enough to be a headline project even then.

---

## 5. `ai-architecture-assistant` — AI Architecture Recommendation Service

**One-line:** A FastAPI service using the Factory Pattern to generate structured architecture recommendations across OpenAI/Hugging Face/Ollama — with a typo that crashes its own default code path.

### Strong points
- Clean 5-file layered structure (`main → architecture_service → llm_factory → config/schemas`) that clearly demonstrates the **Factory Pattern** for LLM provider selection — a legible, textbook example of the pattern.
- Structured output via LangChain's `.with_structured_output()`, not manual JSON parsing.
- Decent input validation via Pydantic `Field` constraints.

### Weak points
- **The default `openai` provider path crashes.** `app/llm_factory.py` references `settings.MODEL_TEMPATURE` — a typo; the real field in `config.py` is `MODEL_TEMPERATURE`. Calling the API with the default provider raises `AttributeError` at runtime, and this typo has been present since the first commit (never fixed across 4 commits).
- **Exception handling bug**: `app/main.py` *returns* an `HTTPException` instead of *raising* it — FastAPI would try to serialize the exception object as a 200 response body instead of returning a proper error.
- **Response schema field typos** (`recomended_tech_stach`, `riks`) that contradict the README's own documented "expected response" and `doc/Test.http` — a direct, checkable contract mismatch.
- Provider abstraction is shallower than advertised: all three "providers" route through the same `ChatOpenAI` client with different base URLs, not genuinely distinct SDK integrations.
- Zero tests, no CI, no Docker, no logging/observability anywhere in the app.
- Dependency file misspelled (`requirement.txt` vs. the README's `requirements.txt`); a stray, unmodified PyCharm scaffold `main.py` at the repo root.

### Plan to close the gaps
1. **Fix the `MODEL_TEMPATURE` → `MODEL_TEMPERATURE` typo** — this single-line fix un-breaks the entire default code path.
2. **Fix the exception handler** to `raise HTTPException(...)` instead of `return`.
3. **Fix the schema field typos** (`riks` → `risks`, `recomended_tech_stach` → `recommended_tech_stack`) and update the README/`Test.http` examples to match.
4. Rename `requirement.txt` → `requirements.txt`; delete the stray PyCharm `main.py`.
5. Add at least a handful of `pytest` cases covering the factory selection and the (now-fixed) happy path — currently zero coverage means zero evidence any of this ever ran successfully.
6. If keeping this project, be explicit that all "providers" share one client class today — either implement a genuinely distinct Hugging Face/Ollama SDK path, or reword the pitch to "OpenAI-compatible endpoint abstraction" rather than "multi-provider."

### Positioning note
Useful only as a **small, clean Factory Pattern illustration** once the bugs are fixed — the pattern itself is legitimate and easy to explain in an interview, but as committed today it would fail on the very first request with the default settings. Fix before mentioning it anywhere.

---

## 6. `intellij-mcp-langgraph-assistant` — MCP Server Reference (`text-polisher`)

**One-line:** A correctly-structured MCP (Model Context Protocol) server demonstrating all three server-side primitives (Resources, Prompts, Tools) — despite the folder name, **no LangGraph is used anywhere in this project**.

### Strong points
- **Genuine, correct MCP implementation**: two `@mcp.resource(...)`, one `@mcp.prompt(...)`, one `@mcp.tool()` — a legible, accurate mapping to the actual protocol's primitive model, not just "wrap an LLM call and call it MCP."
- Structured output via `.with_structured_output(PolishedText)` with a defensive fallback for provider inconsistency — shows awareness of real-world API quirks.
- **Dual transport** (stdio for local dev, streamable-http for Docker/network) controlled by one env var, same code serving both.
- Working Docker + docker-compose deployment (a genuine strength versus most of the other small projects, which have none).
- Best code comments in the portfolio — each section explains *why*, not just what.
- Real review/iteration history: an earlier `main_v0.py` was replaced after a documented "Changes After Review" commit that also deleted training-exercise clutter — this is actual evidence of an engineering review cycle, not just a single commit dump.
- Documentation explicitly states what's *not* implemented (Sampling, Elicitation) — scope honesty rather than overclaiming.

### Weak points
- **The project name and folder are misleading.** "langgraph" appears nowhere in a `pip freeze` or an import statement — there is no multi-agent orchestration, no graph, no branching/looping agentic behavior. This is a single linear LLM chain behind an MCP tool.
- **Environment variable names disagree across three places**: the actual `.env` uses `HUG_API_TOKEN`/`GITHUB_TOKEN`, the code reads `os.getenv("MODEL_API_KEY")`/`LLM_MODEL`, and the README's setup instructions tell users to set `MODEL_API_KEY`/`MODEL_NAME` — following the documented setup as written would not work against the committed `.env`, and the resulting error message references a variable name the code doesn't even check.
- `test.py` is a manual smoke-test script, not an automated test suite — no `pytest`, no assertions.
- No CI, no auth on the HTTP transport (disclosed in the README, which is good practice, but still a real gap beyond localhost).
- Stray 694KB `.gif` committed to the repo root with no explanation in the docs.
- `run.bat` starts a LiteLLM proxy that the rest of the code doesn't actually use — orphaned from the main flow.

### Plan to close the gaps
1. **Rename the project** (folder + README title) to drop "langgraph" — e.g. `mcp-text-polisher` — and reposition it purely as an MCP protocol reference; this removes the single most obvious "gotcha" a technical reviewer would find.
2. **Reconcile the env var names** across `.env`, `app/main.py`, and the README — pick one naming scheme (e.g. `MODEL_API_KEY`/`MODEL_NAME`) and make all three agree; this is the difference between "the README's setup instructions actually work" and not.
3. Convert `test.py` into a real `pytest` suite — at minimum, test `polish_text`'s structured-output parsing with a mocked LLM response.
4. Remove the stray gif and the unused `run.bat`, or document what they're for.
5. Once cleaned up, this is a solid, differentiated "MCP protocol implementation" example — MCP is newer and less commonly demonstrated than LangGraph/RAG, which makes it a good complementary bullet rather than a competing flagship.

### Positioning note
Keep this as a **supplementary MCP-specific** bullet ("built a reference MCP server implementing all three server-side primitives with dual transport") — it demonstrates a different, currently-hot skill (MCP) that none of your other projects cover. Never describe it as a LangGraph project; that claim doesn't survive a `pip freeze` or a `grep`.

---

## Cross-Project Comparison

| Signal | pydanticai | expense-ai | genai-observability | ai-agent-gateway | ai-architecture-assistant | intellij-mcp-langgraph-assistant |
|---|---|---|---|---|---|---|
| Runs as committed | Yes | Yes | Yes | **No — broken import** | **No — crashes on default provider** | Yes (env var mismatch breaks documented setup) |
| Core AI concept | PydanticAI agent, structured output, deterministic testing | LangGraph human-in-the-loop + Postgres checkpointing, RAG | Observability (dual OTel pipelines, sampling, redaction) | LiteLLM provider abstraction, tool routing | Factory Pattern provider abstraction | MCP protocol (Resources/Prompts/Tools) |
| Tests | 106 | 57 | 112 | 4 (partial, on dead code) | 0 | 0 (manual script only) |
| Resilience (retry/breaker) | Timeout budgets, coalescing | Tenacity + PyBreaker | **Missing** (disclosed) | Tenacity retry + fallback | None | None |
| Auth | JWT+RBAC (partial — `/v1` open) | **None** | API key + RBAC | None | None | None (disclosed) |
| Docker | Multi-stage, non-root, healthcheck | Non-root, healthcheck | Present, **runs as root** | None | None | Present |
| CI/CD | None | None | None | None | None | None |
| Git state (main) | **Untracked (0 commits)** | Tracked, 14 commits | **Untracked at current path** | Tracked, 1 mislabeled commit | Tracked, 4 commits (bug never fixed) | Tracked, 7-8 commits incl. review cycle |
| Documentation | Exceptional (597-line README + FAQ) | Exceptional (545-line README) | Exceptional (793-line README + risk register) | Honest but incomplete | Good structure, inaccurate details | Strong, but setup steps don't work as written |

**Portfolio-wide gaps** (true across all six): no CI/CD anywhere, no automated dependency/CVE scanning, all single-developer projects without real production traffic.

---

## Minimum Project(s) for the Resume

**If forced to pick exactly one flagship:** `pydanticai`. It has the broadest single-project concept coverage — hexagonal architecture, a real agent framework, structured output, deterministic agent testing, full observability, security, and production-grade Docker — but it **must be committed to git first**, since it currently has zero history.

**Recommended minimum set — 2 projects:** `pydanticai` + `expense-ai`.
Together they cover essentially every concept an AI Architect / Solution Architect job description asks for:
- Agent frameworks & structured output → `pydanticai`
- Deterministic/offline agent testing → `pydanticai`
- Agentic workflow orchestration with durable state (LangGraph, human-in-the-loop, Postgres checkpointing) → `expense-ai`
- RAG → `expense-ai` (once the embedding function is upgraded — see plan above)
- LLM provider abstraction → both (LiteLLM in `expense-ai`; LiteLLM Proxy in `pydanticai`)
- Resilience patterns (retry, circuit breaker, cache, timeout) → `expense-ai`'s explicit pipeline
- Full observability (OTel traces + metrics) → both
- Layered/hexagonal architecture → both
- Clean, legible git history → `expense-ai` (`pydanticai` needs to be committed first)

**Recommended set — 3 projects, if you have room for one more:** add `genai-observability` for its distinctly deeper **observability-as-a-specialty and security/OWASP** story — no other project in the portfolio matches its sampling strategy, PII redaction layering, or documented risk register, and "observability" is frequently a dedicated line item in AI Architect job descriptions.

**Do not lead with:**
- `ai-agent-gateway` — unrunnable as committed; fix the import bug first if keeping it at all, and even then treat it as a minor supporting example, not a flagship.
- `ai-architecture-assistant` — the default code path crashes; fix the typo and schema mismatches before mentioning it.

**Use only as a supplementary bullet, not a flagship:**
- `intellij-mcp-langgraph-assistant` — legitimate MCP implementation, good for a "hands-on with MCP" line, but rename it and fix the env var mismatch first, and never describe it as involving LangGraph.
