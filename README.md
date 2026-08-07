# ai-architecture-lab

A portfolio of independent, production-shaped reference architectures for AI/agentic system design — agent frameworks, orchestration, observability, resilience, protocol implementation, and provider abstraction — built and audited with the same rigor expected of production systems.

**Author:** Ravi K — Enterprise Solution Architect (TOGAF® 9 Certified) · 19+ years, Financial Services / Supply Chain / AI automation
**LinkedIn:** [linkedin.com/in/ravi-kiran-kumar-kurakula](https://linkedin.com/in/ravi-kiran-kumar-kurakula) · **GitHub:** [github.com/ravik775](https://github.com/ravik775)

---

## Why this repo exists

Each project below isolates one concern of modern AI-system design — an agent framework, a durable orchestration pattern, an observability pipeline, a protocol implementation — rather than bundling everything into one monolith. That separation makes each project's architecture legible on its own and easy to evaluate independently.

**Every technical claim in this README and in [`Project-Portfolio-Analysis.md`](Project-Portfolio-Analysis.md) was verified directly against source code, tests, and `git log` on `main`** — not copied from each project's own marketing copy. Where a project has a known gap, it's disclosed here rather than hidden; the full analysis linked at the bottom documents exact file/line findings and a remediation plan for each one.

## Skills demonstrated across the portfolio

| Concept | Project(s) |
|---|---|
| Agent frameworks (typed tools, structured output) | `pydanticai` (PydanticAI) |
| Deterministic / offline agent testing (zero live LLM calls) | `pydanticai` |
| Agentic orchestration with durable state (human-in-the-loop) | `expense-ai` (LangGraph + PostgreSQL checkpointing) |
| Resilience engineering (retry, circuit breaker, cache, timeout) | `expense-ai` (9-step policy pipeline), `ai-agent-gateway` (partial) |
| RAG / retrieval pipelines | `expense-ai` (ChromaDB-backed policy retrieval) |
| LLM provider abstraction | `ai-agent-gateway`, `expense-ai`, `pydanticai` (all via LiteLLM) |
| Production observability (OTel traces + metrics, sampling) | `pydanticai`, `genai-observability` |
| LLM security (PII redaction, OWASP LLM Top 10, RBAC) | `genai-observability` |
| MCP protocol (Resources / Prompts / Tools) | `intellij-mcp-langgraph-assistant` |
| Hexagonal / layered architecture | `pydanticai`, `expense-ai`, `genai-observability` |
| Factory Pattern (provider selection) | `ai-architecture-assistant` |
| Structured output (Pydantic-validated LLM responses) | `pydanticai`, `expense-ai`, `ai-architecture-assistant`, `intellij-mcp-langgraph-assistant` |
| Docker (multi-stage, non-root, healthcheck) | `pydanticai`, `genai-observability`, `intellij-mcp-langgraph-assistant` |

## Repository map

```
ai-architecture-lab/
├── pydanticai/                        Flagship — PydanticAI agent + dual-pipeline observability
├── expense-ai/                        Flagship — LangGraph human-in-the-loop + resilience pipeline
├── genai-observability/               Specialty — LLM observability & security (OWASP LLM Top 10)
├── ai-agent-gateway/                  Provider abstraction + tool routing (known runtime issue)
├── ai-architecture-assistant/         Factory Pattern reference (known runtime issue)
├── intellij-mcp-langgraph-assistant/  MCP protocol reference (Resources/Prompts/Tools)
├── loan-processing-architecture/      Spring Boot microservices — outside this README's scope
├── gemini-agent/                      Local coding agent — outside this README's scope
└── Project-Portfolio-Analysis.md      Full verified audit: strengths, gaps, remediation, resume guidance
```

---

## Projects

### 1. [`pydanticai`](pydanticai/README.md) — Weather Intelligence Agent 🏳 Flagship

A hexagonal-architecture weather service pairing a **PydanticAI** natural-language agent with a deterministic REST API, full dual-pipeline OpenTelemetry observability, and a self-written 23-question Solution Architect FAQ.

- **Tech stack:** Python, FastAPI, PydanticAI, SQLAlchemy, SQLite, OpenTelemetry, Prometheus, Grafana, Docker
- **Architecture:** `domain` (framework-free models + `Protocol` interfaces) → `application` (services) → `infrastructure` (SQLAlchemy, Open-Meteo HTTP, cache) → `agent` → `api` — swapping the cache or weather provider is additive, not a domain rewrite
- **Highlights:** `Agent` with `FallbackModel`, enforced structured output (`AgentQueryResult`), six typed tools; `FunctionModel`/`TestModel` exercise the full agent loop with **zero live LLM calls**; custom rate-limited trace sampler with RBAC-gated force-trace override via W3C baggage; production Docker hygiene (multi-stage, non-root, `HEALTHCHECK`)
- **Verified:** 106 tests, all external I/O mocked at the protocol boundary
- **Status:** strongest single-project architecture story in the portfolio; pending its first git commit

### 2. [`expense-ai`](expense-ai/README.md) — Agentic Expense Approval Platform 🏳 Flagship

An agentic expense-approval platform where a **LangGraph** state machine routes low-risk expenses to auto-approval and high-value ones into a resumable human-in-the-loop review, durable across process restarts via PostgreSQL checkpointing.

- **Tech stack:** Python, FastAPI, LangGraph, LiteLLM, ChromaDB, PostgreSQL, LangSmith, Docker
- **Architecture:** `StateGraph` with conditional routing and `interrupt()`/`Command(resume=...)`, wrapped in a composable 9-step resilience pipeline (`observability → provider_selection → retrieval → prompt_preparation → guardrail → cache → retry → circuit_breaker → timeout`), each policy an independently testable single-purpose module
- **Highlights:** genuine LiteLLM-backed provider abstraction with a `MockLLMService` for testing; RAG wired end-to-end (ChromaDB retrieval as a pipeline policy); structured Pydantic output validation; cost/token tracking; two operating modes (basic vs. agentic) toggled by config
- **Verified:** 57 tests (~0.63:1 test-to-code ratio), clean 14-commit incremental history mapped to the README's own module-completion table
- **Status:** strongest durable, human-in-the-loop orchestration story in the portfolio

### 3. [`genai-observability`](genai-observability/README.md) — GenAI Observability Reference Service

A deliberately minimal chat service whose real purpose is the observability and security plumbing around it: dual OpenTelemetry pipelines, head+tail sampling, vendor-agnostic export, layered PII redaction, and a documented OWASP LLM Top 10 self-assessment.

- **Tech stack:** Python, FastAPI, OpenTelemetry, OTel Collector, Prometheus/Grafana, Langfuse/LangSmith (pluggable), Docker
- **Architecture:** two independent OTel pipelines (traces vs. metrics — Langfuse/LangSmith don't ingest OTLP metrics), config-driven vendor swap (`OBSERVABILITY_PROVIDER=collector|langfuse_direct|langsmith_direct|console`) with application code depending only on the standard `opentelemetry` API
- **Highlights:** head-based (SDK ratio) + tail-based (Collector "always keep errors") sampling split; custom `ForceTraceSampler` via OTel `Baggage`; 4-layer defense-in-depth PII redaction (one layer explicitly documented as not-yet-built rather than glossed over); API-key + RBAC auth with per-key token-bucket rate limiting; a documented risk register (`docs/SECURITY-PLAN.md`) mapped to shipped files
- **Verified:** 112 tests, ruff-clean, correct use of OTel GenAI semantic conventions (`gen_ai.system`, `gen_ai.usage.*`)
- **Status:** deepest observability-as-a-specialty story in the portfolio; pending commit at its current path

### 4. [`ai-agent-gateway`](ai-agent-gateway/README.md) — AI Agent Gateway

A small FastAPI gateway routing questions to a weather/calculator/web-search tool or a general LLM completion via LiteLLM's provider-agnostic interface.

- **Tech stack:** Python, FastAPI, LiteLLM, Tenacity
- **Architecture:** `api → services → tools`; calculator tool uses an AST-based safe evaluator instead of `eval()`; a more sophisticated confidence-scored hybrid rule+LLM router exists in the codebase alongside the simpler one that's actually wired in
- **Status:** ⚠️ known issue — a module-level indentation fault currently prevents the app from starting as committed; see the full analysis for the exact fix. Kept in the portfolio as a small provider-abstraction/tool-routing reference, not a flagship.

### 5. [`ai-architecture-assistant`](ai-architecture-assistant/README.md) — AI Architecture Recommendation Service

A FastAPI service that turns a business requirement into a structured architecture recommendation, using the **Factory Pattern** to decouple business logic from the underlying LLM provider (OpenAI / Hugging Face / Ollama).

- **Tech stack:** Python, FastAPI, LangChain, Pydantic
- **Architecture:** clean 5-file layering (`main → architecture_service → llm_factory → config/schemas`) — a legible, textbook illustration of the Factory Pattern for provider selection; structured output via LangChain's `.with_structured_output()`
- **Status:** ⚠️ known issue — a config-field typo currently crashes the default provider path at runtime; see the full analysis for the exact fix. Kept as a clean, minimal Factory Pattern illustration once corrected.

### 6. [`intellij-mcp-langgraph-assistant`](intellij-mcp-langgraph-assistant/Readme.md) — MCP Server Reference

A correctly-structured **Model Context Protocol (MCP)** server implementing all three server-side primitives — Resources, Prompts, and Tools — around a text-polishing example.

- **Tech stack:** Python, FastMCP, LangChain, Docker
- **Architecture:** two `@mcp.resource(...)`, one `@mcp.prompt(...)`, one `@mcp.tool()`; dual transport (stdio for local dev, streamable-http for Docker/network) controlled by a single env var, same code serving both
- **Highlights:** structured output with a defensive fallback for provider inconsistency; working Docker + docker-compose deployment; real review/iteration history (an earlier version was replaced after a documented review pass); documentation explicitly states what's *not* implemented (Sampling, Elicitation) rather than overclaiming
- **Note:** despite the folder name, this project does not use LangGraph — it's an MCP protocol reference, positioned here as a "hands-on with MCP" example (MCP is newer and less commonly demonstrated than LangGraph/RAG)

---

## Cross-project comparison

| Signal | pydanticai | expense-ai | genai-observability | ai-agent-gateway | ai-architecture-assistant | intellij-mcp-langgraph-assistant |
|---|---|---|---|---|---|---|
| Runs as committed | Yes | Yes | Yes | No — known import issue | No — known config typo | Yes |
| Core AI concept | Agent framework, structured output, deterministic testing | LangGraph human-in-the-loop + durable state, RAG | Observability (dual OTel pipelines, sampling, redaction) | LLM provider abstraction, tool routing | Factory Pattern provider abstraction | MCP protocol (Resources/Prompts/Tools) |
| Tests | 106 | 57 | 112 | 4 | 0 | Manual script only |
| Resilience (retry/breaker) | Timeout budgets, coalescing | Tenacity + PyBreaker (full pipeline) | Not yet implemented (disclosed) | Tenacity retry + fallback | None | None |
| Auth | JWT + RBAC (partial) | None yet | API key + RBAC | None | None | None (disclosed) |
| Docker | Multi-stage, non-root, healthcheck | Non-root, healthcheck | Present (runs as root) | None | None | Present |
| Documentation | 597-line README + 23-Q FAQ | 545-line README | 793-line README + risk register | Honest, but incomplete | Structured | Strong |

**Portfolio-wide, honestly disclosed gaps:** no CI/CD pipeline on any project yet; no automated dependency/CVE scanning; all are single-developer projects without real production traffic.

## Full technical audit

[`Project-Portfolio-Analysis.md`](Project-Portfolio-Analysis.md) contains the complete project-by-project breakdown: verified strong points, verified weak points (specific files/lines, checked against code and `git log` rather than each README's own claims), a prioritized remediation plan per project, and resume/interview positioning guidance — including which two projects (`pydanticai` + `expense-ai`) together cover the broadest set of AI-architecture concepts for a resume headline.

## Scope note

[`loan-processing-architecture`](loan-processing-architecture/Readme.md) (a Spring Boot microservices loan-processing system) and [`gemini-agent`](gemini-agent/README.md) (a local coding agent) live in this repository but are outside the scope of the analysis above.
