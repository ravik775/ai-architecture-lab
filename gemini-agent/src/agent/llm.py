"""A minimal LangChain `BaseChatModel` that routes calls through LiteLLM.

`langgraph`'s `create_react_agent` needs a chat model with reliable
`bind_tools()` / tool-call parsing. Rather than depend on the community
LiteLLM wrapper (whose tool-calling support varies by version), this talks to
`litellm.completion` directly using the standard OpenAI-style `tools` schema,
which litellm translates for Gemini (or any other provider) under the hood.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional, Sequence, Union

import litellm
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

# Some providers/models reject OpenAI-style params they don't support (e.g.
# `parallel_tool_calls`) instead of ignoring them. drop_params makes litellm
# silently strip anything the target provider can't handle, which keeps a
# single call_kwargs shape portable across very different backends.
litellm.drop_params = True


def _message_to_openai_dict(message: BaseMessage) -> dict:
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    if isinstance(message, AIMessage):
        out: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                }
                for tc in message.tool_calls
            ]
        return out
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    raise ValueError(f"Unsupported message type: {type(message)}")


# Anything indicating THIS model isn't usable right now — out of capacity,
# out of credits, or no longer exists on the provider. All of these are
# fixed by trying the next model in the chain. Deliberately excludes things
# like malformed-request or auth-key errors, which would fail identically
# on every model and shouldn't be silently retried.
_MODEL_UNAVAILABLE_MARKERS = (
    "rate limit",
    "ratelimiterror",
    "429",
    "resourceexhausted",
    "resource_exhausted",
    "quota",
    "insufficient_quota",
    "capacity",
    "overloaded",
    "out of credits",
    "worker local total request limit",
    "no endpoints found",
    "model_not_found",
    "notfounderror",
    "does not exist",
    "no longer available",
    "requires more credits",
    "insufficient balance",
    "add credits",
    "payment required",
    "402",
)


def is_capacity_error(exc: BaseException) -> bool:
    """True if `exc` means this specific model is currently unusable — rate
    limited, out of credits/capacity, or no longer offered by the provider —
    as opposed to a genuine request bug. Used to decide whether falling back
    to the next model in the chain is appropriate (another model won't fix a
    malformed request, but it will fix "this model is gone/exhausted")."""
    text = str(exc).lower()
    return any(marker in text for marker in _MODEL_UNAVAILABLE_MARKERS)


def _parse_tool_calls(raw_tool_calls: Any) -> list[dict]:
    parsed = []
    for tc in raw_tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        parsed.append({"name": tc.function.name, "args": args, "id": tc.id, "type": "tool_call"})
    return parsed


def _extract_fallback_tool_call(content: str, valid_tool_names: set[str]) -> Optional[dict]:
    """Some models — especially smaller/weaker ones, seen repeatedly with
    small local models via Ollama — describe a tool call as plain JSON text
    in the message content instead of using the API's structured
    tool-calling mechanism, even when given a `tools` schema. If the whole
    response is exactly one such JSON object naming a real bound tool,
    treat it as if the API had returned it as a proper tool call, rather
    than showing raw JSON to the user as if it were a text reply."""
    text = content.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    name = payload.get("name")
    args = payload.get("arguments", payload.get("parameters"))
    if not isinstance(name, str) or name not in valid_tool_names or not isinstance(args, dict):
        return None
    return {"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}", "type": "tool_call"}


class LiteLLMChatModel(BaseChatModel):
    """LangChain-compatible chat model backed by `litellm.completion`."""

    model: str
    api_key: Optional[str] = None
    temperature: float = 0.2
    # Left unset, some models (e.g. Claude via OpenRouter) default to
    # requesting an enormous max_tokens (65536+), which fails outright on
    # accounts without enough remaining balance to cover that ceiling, even
    # though the actual response would've been far shorter. A capped
    # default avoids that failure mode without being too tight for a
    # normal file-edit response.
    max_tokens: Optional[int] = 8192
    # Ollama's default context window is 4096 tokens regardless of what the
    # underlying model actually supports. Our system prompt + 6 tool
    # schemas + conversation history blow past that fast (a single large
    # user message can exceed it alone), silently truncating older context
    # - including, worst case, the tool definitions themselves, which
    # manifests as the model printing a tool call as plain JSON text
    # instead of actually invoking it. None = leave provider default
    # (non-Ollama models ignore this field entirely, see below).
    num_ctx: Optional[int] = None
    bound_tools: list[dict] = Field(default_factory=list)
    # litellm's own retry (exponential backoff) for transient errors -
    # rate limits, provider capacity, timeouts - common on free-tier models.
    # Doesn't help once a provider is genuinely out of capacity for a while,
    # but absorbs short blips without surfacing an error at all.
    num_retries: int = 2

    @property
    def _llm_type(self) -> str:
        return "litellm-chat"

    def bind_tools(
        self, tools: Sequence[Union[dict, type, BaseTool]], **kwargs: Any
    ) -> "LiteLLMChatModel":
        formatted = [convert_to_openai_tool(t) for t in tools]
        return self.__class__(
            model=self.model,
            api_key=self.api_key,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            num_ctx=self.num_ctx,
            bound_tools=formatted,
            num_retries=self.num_retries,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        call_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [_message_to_openai_dict(m) for m in messages],
            "temperature": self.temperature,
        }
        # litellm forwards num_retries into huggingface_hub's InferenceClient
        # constructor as `max_retries`, which that client doesn't accept -
        # litellm.drop_params covers unsupported API-payload params, not
        # this SDK-constructor-level kwarg, so it logs a warning every call
        # instead. Skip it for this provider rather than spam harmless noise.
        if not self.model.startswith("huggingface/"):
            call_kwargs["num_retries"] = self.num_retries
        if self.model.startswith("ollama_chat/") or self.model.startswith("ollama/"):
            # A modest safety-net bump over Ollama's 4096 default - not the
            # primary fix for large prompts. Relying on ever-larger context
            # windows to cover growing conversation history costs RAM/CPU
            # and still degrades: the right fix is keeping each turn's
            # actual prompt small (phased, focused instructions) rather
            # than accumulating an entire spec into every request.
            call_kwargs["num_ctx"] = self.num_ctx or 8192
        if self.api_key:
            call_kwargs["api_key"] = self.api_key
        if self.max_tokens:
            call_kwargs["max_tokens"] = self.max_tokens
        if stop:
            call_kwargs["stop"] = stop
        if self.bound_tools:
            call_kwargs["tools"] = self.bound_tools
            # Some models/providers emit multiple tool_calls in one response
            # and then hard-reject the request if their backend can't
            # actually execute more than one per turn (seen on OpenRouter
            # with small models routed through CoreWeave/Groq). Forcing one
            # tool call per turn avoids that whole error class; it costs an
            # extra round trip when the model would've batched calls, not
            # correctness.
            call_kwargs["parallel_tool_calls"] = False

        response = litellm.completion(**call_kwargs)
        message = response.choices[0].message

        content = message.content or ""
        tool_calls = _parse_tool_calls(getattr(message, "tool_calls", None))
        if not tool_calls and self.bound_tools:
            valid_names = {t["function"]["name"] for t in self.bound_tools}
            fallback = _extract_fallback_tool_call(content, valid_names)
            if fallback:
                tool_calls = [fallback]
                content = ""

        ai_message = AIMessage(content=content, tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=ai_message)])
