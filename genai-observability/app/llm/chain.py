"""
Minimal LangGraph pipeline around litellm -> OpenRouter.

The use case is intentionally trivial (stateless chat with in-memory
history) - per the requirements, the point of this file is to be a
*realistic shape* (graph with distinct nodes, each independently traced)
for the observability layer to hang off of, not to demonstrate advanced
LangGraph features.

Span hierarchy produced by one call to `run_chat_graph`:

    chat.request                (opened by the API route)
      graph.execute
        node.load_memory
        node.llm_generate
          litellm.completion    (gen_ai.* attributes: model, tokens, cost)
        node.persist_memory
"""
from __future__ import annotations

import logging
import time
from typing import TypedDict

import litellm
from langgraph.graph import END, START, StateGraph
from opentelemetry.trace import SpanKind

from app.config import Settings
from app.llm.memory import Message, store
from app.observability.metrics import get_app_metrics
from app.observability.tracing import (
    set_llm_request_attributes,
    set_llm_response_attributes,
    traced_span,
)

logger = logging.getLogger("app.llm")

SYSTEM_PROMPT = (
    "You are a concise, helpful assistant embedded in a reference "
    "observability platform. Keep answers short and factual."
)


class GraphState(TypedDict, total=False):
    session_id: str
    user_message: str
    history: list[Message]
    llm_messages: list[dict]
    assistant_message: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    finish_reason: str
    latency_ms: float


def _node_load_memory(state: GraphState) -> GraphState:
    with traced_span(
        "node.load_memory",
        attributes={"app.session_id": state["session_id"]},
    ) as span:
        history = store.get_history(state["session_id"])
        llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        llm_messages.extend({"role": m["role"], "content": m["content"]} for m in history)
        llm_messages.append({"role": "user", "content": state["user_message"]})
        span.set_attribute("app.memory.turns_loaded", len(history))
        return {**state, "history": history, "llm_messages": llm_messages}


def _node_llm_generate(state: GraphState, settings: Settings) -> GraphState:
    with (
        traced_span("node.llm_generate", attributes={"app.session_id": state["session_id"]}),
        traced_span("litellm.completion", kind=SpanKind.CLIENT) as span,
    ):
        set_llm_request_attributes(
            span,
            system="openrouter",
            model=settings.openrouter_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        start = time.perf_counter()
        response = litellm.completion(
            model=settings.openrouter_model,
            messages=state["llm_messages"],
            api_key=settings.openrouter_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_request_timeout_seconds,
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        try:
            cost_usd = litellm.completion_cost(completion_response=response)
        except Exception:  # noqa: BLE001 - cost lookup is best-effort
            cost_usd = None

        set_llm_response_attributes(
            span,
            model=response.model,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            finish_reason=choice.finish_reason,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

        # Metrics pipeline, alongside the span above: this is what lets
        # you graph request rate / token cost per minute over time,
        # rather than having to derive it by scanning individual traces.
        get_app_metrics().record_llm_call(
            model=response.model,
            duration_seconds=latency_ms / 1000,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            cost_usd=cost_usd,
        )

        return {
            **state,
            "assistant_message": choice.message.content or "",
            "model": response.model,
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
            "cost_usd": cost_usd or 0.0,
            "finish_reason": choice.finish_reason or "unknown",
            "latency_ms": latency_ms,
        }


def _node_persist_memory(state: GraphState) -> GraphState:
    with traced_span(
        "node.persist_memory",
        attributes={"app.session_id": state["session_id"]},
    ) as span:
        store.append(state["session_id"], "user", state["user_message"])
        store.append(state["session_id"], "assistant", state["assistant_message"])
        span.set_attribute("app.memory.turns_after", len(store.get_history(state["session_id"])))
        return state


def build_graph(settings: Settings):
    graph = StateGraph(GraphState)
    graph.add_node("load_memory", _node_load_memory)
    graph.add_node("llm_generate", lambda s: _node_llm_generate(s, settings))
    graph.add_node("persist_memory", _node_persist_memory)

    graph.add_edge(START, "load_memory")
    graph.add_edge("load_memory", "llm_generate")
    graph.add_edge("llm_generate", "persist_memory")
    graph.add_edge("persist_memory", END)

    return graph.compile()


class ChatGraphRunner:
    """Compiles the graph once and reuses it across requests."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph = build_graph(settings)

    def run(self, session_id: str, user_message: str) -> GraphState:
        with traced_span(
            "graph.execute",
            attributes={"app.session_id": session_id, "app.graph.name": "chat_graph"},
        ):
            result: GraphState = self._graph.invoke(
                {"session_id": session_id, "user_message": user_message}
            )
            return result
