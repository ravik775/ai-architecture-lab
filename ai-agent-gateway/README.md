# Production-Style AI Agent Gateway

Provider-agnostic Python AI Agent using **Pydantic + LiteLLM + FastAPI**.

The app routes user questions to tools:

- Weather tool using Open-Meteo public APIs
- Calculator tool for arithmetic
- Web search tool for general internet questions
- LiteLLM-based LLM client abstraction for provider independence

## Architecture

```text
Client
  -> FastAPI API
  -> AgentService
  -> IntentRouter
  -> ToolRegistry
       -> WeatherTool / CalculatorTool / WebSearchTool
  -> LLMClient using LiteLLM
       -> OpenAI / Hugging Face / Bedrock / Azure OpenAI / local OpenAI-compatible server
```

The application depends on `LLMClient`, not a vendor SDK. LiteLLM gives a unified OpenAI-style interface across many providers.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Set your key in `.env`:

```bash
OPENAI_API_KEY=sk-...
DEFAULT_MODEL=openai/gpt-4o-mini
```

Run:

```bash
uvicorn app.main:app --reload --port 8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

## Try Requests

Weather:

```bash
curl -X POST http://127.0.0.1:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the weather in Tokyo?"}'
```

Calculation:

```bash
curl -X POST http://127.0.0.1:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"Calculate 100 + 200"}'
```

Internet:

```bash
curl -X POST http://127.0.0.1:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"message":"Who is the current CEO of Microsoft?"}'
```

## Hugging Face Router Example

```bash
DEFAULT_MODEL=huggingface/Qwen/Qwen2.5-7B-Instruct
HUGGINGFACE_API_KEY=hf_xxx
LITELLM_API_BASE=https://router.huggingface.co/v1
```

Provider support can vary. If a provider/model rejects some parameters, configure LiteLLM/provider settings accordingly.

## Production Notes

For real production:

- Put API keys in Secret Manager, not `.env`.
- Add auth, rate limiting, request quotas, and audit logs.
- Use Redis for response/tool-result caching.
- Add OpenTelemetry traces and structured logs.
- Use LiteLLM Proxy if multiple apps need centralized routing, budget controls, and observability.
- Replace DDGS with a paid search API if SLA is required.
