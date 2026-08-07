"""Agent construction and the run-level service wrapper (latency budget,
metrics, token/cost accounting). PydanticAI talks to the LLM only through
LiteLLM Proxy's OpenAI-compatible `/v1` endpoint - never directly to a
provider, and never on the deterministic weather path (see
`weather_service.py`)."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from pydantic_ai import Agent, UnexpectedModelBehavior
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app.agent.deps import AgentDeps
from app.agent.schemas import AgentQueryResult
from app.agent.tools import AGENT_TOOLS
from app.config.settings import AgentSettings
from app.domain.errors import AgentTimeoutError
from app.observability.metrics import (
    agent_run_duration_seconds,
    agent_runs_total,
    litellm_request_duration_seconds,
    llm_estimated_cost_usd_total,
    llm_tokens_total,
    structured_output_failures_total,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a weather assistant that answers questions using ONLY the provided tools.

Rules you must follow exactly:
1. Never state a location is supported, or invent a location_id, unless it came
   from `resolve_supported_location` or `list_supported_locations`.
2. To resolve a place name from the user's message, call `resolve_supported_location`.
   If it returns resolved=false, do NOT guess: set needs_clarification=true, copy its
   candidates into clarification_options, and write an answer asking the user to pick one.
   If candidates is empty, say the location isn't supported - do not suggest an unconfigured city.
3. Only call `get_current_weather` with a location_id you obtained from tools, never a raw
   place name.
4. Never invent a temperature, weather code, or any other weather value. If
   `get_current_weather` returns an "error" field, report that the weather is
   temporarily unavailable for that location and leave the `weather` field unset -
   never substitute a plausible-looking guess.
5. Preserve the exact units and observation_time_utc returned by the tools -
   temperatures are Celsius, wind speed is km/h, precipitation is mm.
6. If the resolved location has `is_state_representative: true`, you MUST set
   `used_representative_location=true` and write a `representative_disclaimer`
   explaining the result is for that specific city, not an average for the
   whole state/province.
7. Keep `answer` concise (2-4 sentences) and grounded only in tool results.
"""


def build_agent(settings: AgentSettings, *, model: Model | None = None) -> Agent[AgentDeps, AgentQueryResult]:
    if model is None:
        provider = OpenAIProvider(
            base_url=f"{settings.litellm_base_url.rstrip('/')}/v1", api_key=settings.litellm_api_key
        )
        model_settings = ModelSettings(
            temperature=settings.temperature,
            max_tokens=settings.max_output_tokens,
            timeout=settings.request_timeout_seconds,
        )
        primary = OpenAIChatModel(settings.model_alias, provider=provider, settings=model_settings)
        fallback = OpenAIChatModel(settings.fallback_model_alias, provider=provider, settings=model_settings)
        model = FallbackModel(primary, fallback)

    return Agent(
        model,
        output_type=AgentQueryResult,
        deps_type=AgentDeps,
        system_prompt=SYSTEM_PROMPT,
        tools=AGENT_TOOLS,
        retries=2,
    )


class AgentQueryOutcome:
    __slots__ = ("result", "duration_ms", "tool_calls")

    def __init__(self, result: AgentQueryResult, duration_ms: float, tool_calls: list[str]) -> None:
        self.result = result
        self.duration_ms = duration_ms
        self.tool_calls = tool_calls


class AgentService:
    def __init__(
        self,
        agent: Agent[AgentDeps, AgentQueryResult],
        deps_factory: Callable[[], AgentDeps],
        settings: AgentSettings,
    ) -> None:
        self._agent = agent
        self._deps_factory = deps_factory
        self._settings = settings

    async def query(self, message: str) -> AgentQueryOutcome:
        deps = self._deps_factory()
        started = time.perf_counter()

        try:
            run_result = await asyncio.wait_for(
                self._agent.run(message, deps=deps),
                timeout=self._settings.total_latency_budget_seconds,
            )
        except TimeoutError as exc:
            agent_runs_total.labels(status="failure").inc()
            agent_run_duration_seconds.observe(time.perf_counter() - started)
            raise AgentTimeoutError(
                f"agent did not respond within {self._settings.total_latency_budget_seconds}s"
            ) from exc
        except UnexpectedModelBehavior:
            structured_output_failures_total.inc()
            agent_runs_total.labels(status="failure").inc()
            agent_run_duration_seconds.observe(time.perf_counter() - started)
            raise
        except Exception:
            agent_runs_total.labels(status="failure").inc()
            agent_run_duration_seconds.observe(time.perf_counter() - started)
            raise

        duration = time.perf_counter() - started
        agent_run_duration_seconds.observe(duration)
        status = "clarification_needed" if run_result.output.needs_clarification else "success"
        agent_runs_total.labels(status=status).inc()

        usage = run_result.usage
        if usage is not None:
            litellm_request_duration_seconds.observe(duration)
            if usage.input_tokens:
                llm_tokens_total.labels(direction="input").inc(usage.input_tokens)
            if usage.output_tokens:
                llm_tokens_total.labels(direction="output").inc(usage.output_tokens)
            cost = getattr(usage, "cost", None)
            if cost:
                llm_estimated_cost_usd_total.inc(float(cost))

        tool_calls = [
            part.tool_name
            for message_ in run_result.all_messages()
            for part in getattr(message_, "parts", [])
            if isinstance(part, ToolCallPart)
        ]

        return AgentQueryOutcome(result=run_result.output, duration_ms=duration * 1000, tool_calls=tool_calls)
