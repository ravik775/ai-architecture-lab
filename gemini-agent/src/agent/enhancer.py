"""Optional prompt-enhancement pass: rewrites a raw user prompt into a
clearer, more actionable one using a small/cheap model, before it's sent to
the main coding agent."""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.llm import LiteLLMChatModel
from src.agent.prompts import PROMPT_ENHANCER_SYSTEM_PROMPT

_DELIMITER_RE = re.compile(r"<<<PROMPT>>>\s*(.*?)\s*<<<END>>>", re.DOTALL)


def enhance_prompt(raw_prompt: str, model: str, api_key: str | None) -> tuple[str, bool]:
    """Return (text, was_enhanced).

    Small local models sometimes ignore the rewrite-only instruction and try
    to directly solve/answer the request instead (e.g. writing code for
    "make a calculator" instead of a clearer prompt describing one). The
    system prompt requires the real rewrite to be wrapped in a fixed
    <<<PROMPT>>>...<<<END>>> delimiter specifically so that failure mode is
    cheaply detectable: if the delimiter isn't there, the model went off
    script, and we fall back to the original prompt untouched rather than
    risk showing broken output in its place.
    """
    llm = LiteLLMChatModel(model=model, api_key=api_key, temperature=0.3, num_retries=1)
    response = llm.invoke(
        [
            SystemMessage(content=PROMPT_ENHANCER_SYSTEM_PROMPT),
            HumanMessage(content=raw_prompt),
        ]
    )
    match = _DELIMITER_RE.search(response.content or "")
    if not match:
        return raw_prompt, False

    rewritten = match.group(1).strip()
    return (rewritten, True) if rewritten else (raw_prompt, False)
