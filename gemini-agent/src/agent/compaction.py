"""Keeps each turn's effective prompt bounded regardless of how long the
conversation has grown, by summarizing older history into a compact note
once it crosses a size threshold.

Applies to every provider/model, not just local ones — a smaller prompt is
faster and cheaper everywhere (fewer tokens billed on paid APIs, less
prefill time on local CPU inference), and it's what actually keeps small
models from being overwhelmed by their own accumulated history, rather than
just raising the context-window ceiling and hoping the model still copes
with everything in it.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agent.llm import LiteLLMChatModel

# Rough proxy for token count (no per-model tokenizer available) - most
# models average ~4 chars/token, so this is a conservative ~2500-token cap
# that's small even for local models, while still generous for normal use.
COMPACTION_THRESHOLD_CHARS = 10_000

# Always keep at least this many trailing messages verbatim - compaction
# only ever touches older history, never the turn the model is about to see.
KEEP_RECENT_MESSAGES = 6

_SUMMARY_PROMPT = (
    "Summarize the conversation so far in under 150 words, preserving: what "
    "the user is trying to build or accomplish, key decisions or "
    "constraints already established, and any files already created or "
    "changed. Write it as a factual note for continuing the conversation, "
    "not a transcript. Output only the summary."
)


def _find_safe_cut_index(messages: list[BaseMessage], target_index: int) -> int:
    """Nearest index <= target_index that starts a fresh human turn, so a
    tool-call/tool-result pair is never split across the summary boundary
    (a dangling ToolMessage with no preceding AIMessage.tool_calls would
    break the next request)."""
    for i in range(target_index, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return 0


def maybe_compact_history(
    messages: list[BaseMessage], model: str, api_key: str | None
) -> tuple[list[BaseMessage], bool]:
    """Return (possibly-compacted messages, was_compacted)."""
    total_chars = sum(len(m.content or "") for m in messages)
    if total_chars <= COMPACTION_THRESHOLD_CHARS or len(messages) <= KEEP_RECENT_MESSAGES:
        return messages, False

    cut = _find_safe_cut_index(messages, len(messages) - KEEP_RECENT_MESSAGES)
    if cut <= 0:
        return messages, False  # no safe boundary to cut at - leave as-is

    older, recent = messages[:cut], messages[cut:]
    transcript = "\n".join(
        f"{m.__class__.__name__}: {(m.content or '')[:500]}"
        for m in older
        if isinstance(m, (HumanMessage, AIMessage)) and m.content
    )
    if not transcript.strip():
        return messages, False

    try:
        llm = LiteLLMChatModel(model=model, api_key=api_key, temperature=0.2, num_retries=1)
        response = llm.invoke(
            [SystemMessage(content=_SUMMARY_PROMPT), HumanMessage(content=transcript)]
        )
        summary_text = (response.content or "").strip()
    except Exception:
        return messages, False  # compaction failing must never break the real turn

    if not summary_text:
        return messages, False

    summary_message = SystemMessage(content=f"[Earlier conversation summary]\n{summary_text}")
    return [summary_message, *recent], True
