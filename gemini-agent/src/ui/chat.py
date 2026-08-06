"""Chat panel: message history, optional prompt enhancement, and agent invocation."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from src.agent.enhancer import enhance_prompt
from src.agent.graph import build_agent
from src.agent.llm import LiteLLMChatModel, is_capacity_error
from src.agent.prompts import build_system_prompt
from src.agent.tools import build_tools
from src.config import AGENT_RECURSION_LIMIT, PROMPT_ENHANCER, get_api_key
from src.persistence import save_exhausted_models

# Matches the pending-changes panel's height so both side-by-side panes scroll
# independently within their own bounded box, the same way the native
# Streamlit sidebar already does - scrolling through chat history should
# never carry the other panes along with it.
HISTORY_HEIGHT = 560


def _run_agent_turn(project_root: str) -> None:
    """Run one agent turn, walking the configured model chain on failure.

    Streaming (rather than a single .invoke()) means a failure partway
    through a multi-tool-call turn - e.g. hitting a rate limit after the
    2nd of 3 needed file edits - doesn't discard the message history for
    the 1st edit, which already succeeded. If the active model turns out
    to be rate-limited/out of credits, the next model in the sidebar's
    priority list is tried automatically with no interruption; only if
    every configured model fails do we surface an error.
    """
    exhausted = st.session_state.setdefault("exhausted_models", {})
    full_chain = st.session_state.get("model_chain") or [st.session_state.model]
    chain = [m for m in full_chain if m not in exhausted] or full_chain

    # Tools/system prompt don't depend on which model is active - build them
    # once per turn instead of re-building (and recompiling a fresh LangGraph
    # graph) on every fallback attempt in the loop below.
    tools = build_tools(Path(project_root), st.session_state.pending_store)
    system_prompt = build_system_prompt(project_root, st.session_state.get("project_summary"))

    st.session_state.turn_fallback_note = None
    st.session_state.turn_attempts = []
    last_error: str | None = None

    for i, model in enumerate(chain):
        llm = LiteLLMChatModel(model=model, api_key=st.session_state.api_key)
        agent = build_agent(llm, tools, system_prompt)
        label = f"Thinking… ({model})" if len(chain) > 1 else "Thinking…"
        with st.spinner(label):
            try:
                for step in agent.stream(
                    {"messages": st.session_state.lc_messages},
                    config={"recursion_limit": AGENT_RECURSION_LIMIT},
                    stream_mode="values",
                ):
                    st.session_state.lc_messages = step["messages"]
                st.session_state.turn_error = None
                st.session_state.turn_attempts.append((model, "succeeded"))
                if i > 0:
                    st.session_state.turn_fallback_note = (
                        f"Switched to `{model}` — earlier model(s) in your list were "
                        "rate-limited or out of credits."
                    )
                return
            except Exception as exc:  # noqa: BLE001 - surface any provider/network error
                last_error = str(exc)
                if is_capacity_error(exc):
                    exhausted[model] = last_error
                    save_exhausted_models(exhausted)
                    st.session_state.turn_attempts.append((model, "rate-limited/unavailable"))
                    continue
                st.session_state.turn_attempts.append((model, "error"))
                st.session_state.turn_error = last_error
                return

    st.session_state.turn_error = (
        f"All {len(chain)} configured model(s) are currently rate-limited or unavailable. "
        f"Last error: {last_error}"
    )


def _submit_prompt(prompt: str, project_root: str, container) -> None:
    st.session_state.lc_messages.append(HumanMessage(content=prompt))
    with container, st.chat_message("user"):
        st.markdown(prompt)
    with container, st.chat_message("assistant"):
        _run_agent_turn(project_root)
        if st.session_state.get("turn_fallback_note"):
            st.info(st.session_state.turn_fallback_note)
        if not st.session_state.get("turn_error"):
            final_text = next(
                (
                    m.content
                    for m in reversed(st.session_state.lc_messages)
                    if isinstance(m, AIMessage) and m.content
                ),
                None,
            )
            st.markdown(final_text or "_(no response text — check pending changes for staged edits)_")


def _enhancer_model_and_key() -> tuple[str, str | None] | None:
    """Always use the fixed enhancer model from config/models.yaml — it
    never follows whatever provider/model the user picked for chat. Returns
    None only if that fixed model's own key (if it needs one) isn't set."""
    model = PROMPT_ENHANCER.get("model")
    if not model:
        return None
    required_vars = PROMPT_ENHANCER.get("api_key_env_vars") or ()
    if not required_vars:
        return model, None  # e.g. a local Ollama model - no key needed
    key = get_api_key(required_vars)
    return (model, key) if key else None


def _clear_conversation() -> None:
    st.session_state.lc_messages = []
    st.session_state.turn_error = None
    st.session_state.turn_fallback_note = None
    st.session_state.turn_attempts = []
    st.session_state.pending_enhancement = None


def _scroll_chat_to_bottom() -> None:
    """st.container(height=...) doesn't auto-scroll to new content, so a
    reply can land below the fold with no visible sign a message arrived.
    A tiny same-origin iframe script (not a JS library) is the standard,
    low-overhead way to fix this in Streamlit. `window.top` (not
    `window.parent`) because some deployments nest the app more than one
    frame deep - `top` always reaches the outermost document regardless."""
    st.components.v1.html(
        """<script>
        const box = window.top.document.querySelector('.st-key-chat_history');
        if (box) { box.scrollTop = box.scrollHeight; }
        </script>""",
        height=0,
    )


def render_chat() -> None:
    header_col, button_col = st.columns([5, 1])
    header_col.caption(f"Chatting with `{st.session_state.get('model', '')}`")
    if button_col.button("🗑️ New chat", disabled=not st.session_state.lc_messages):
        _clear_conversation()
        st.rerun()

    history = st.container(height=HISTORY_HEIGHT, key="chat_history")
    with history:
        if not st.session_state.lc_messages:
            st.caption(
                "👋 Select a project folder in the sidebar, then ask the agent to explain, "
                "review, or modify code — e.g. \"add a .gitignore\" or \"explain what main.py does\"."
            )
        for msg in st.session_state.lc_messages:
            if isinstance(msg, HumanMessage):
                with st.chat_message("user"):
                    st.markdown(msg.content)
            elif isinstance(msg, AIMessage) and msg.content:
                with st.chat_message("assistant"):
                    st.markdown(msg.content)
    if st.session_state.lc_messages:
        _scroll_chat_to_bottom()

    project_root = st.session_state.get("project_root")
    project_root_valid = bool(project_root) and Path(project_root).is_dir()

    if st.session_state.get("turn_error"):
        st.error(f"Agent error: {st.session_state.turn_error}")
        st.caption(
            "Any tool calls that already succeeded before this error are kept (check "
            "Pending Changes). Resume continues this same request instead of starting over."
        )
        attempts = st.session_state.get("turn_attempts") or []
        if attempts:
            st.caption(
                "Models tried this turn: "
                + ", ".join(f"`{model}` ({outcome})" for model, outcome in attempts)
            )
        if st.button("Resume", disabled=not project_root_valid):
            with history, st.chat_message("assistant"):
                _run_agent_turn(project_root)
            st.rerun()

    pending = st.session_state.get("pending_enhancement")
    if pending:
        with st.container(border=True):
            st.caption("Your prompt:")
            st.markdown(f"*{pending['original']}*")
            st.caption(f"✨ Enhanced by `{pending['model']}` — edit if you like, then send:")
            edited = st.text_area(
                "Enhanced prompt", value=pending["enhanced"], label_visibility="collapsed", height=100
            )
            col1, col2 = st.columns(2)
            if col1.button("Send", type="primary", disabled=not project_root_valid):
                final_prompt = edited.strip() or pending["original"]
                st.session_state.pending_enhancement = None
                _submit_prompt(final_prompt, project_root, history)
                st.rerun()
            if col2.button("Cancel"):
                st.session_state.pending_enhancement = None
                st.rerun()
        return

    st.checkbox(
        "✨ Enhance prompt before sending",
        key="enhance_prompt_enabled",
        help=(
            "Rewrites your message into a clearer, more specific prompt using a small model "
            "before it goes to the coding agent. You review and can edit it before it's sent."
        ),
    )

    has_model = bool(st.session_state.get("model_chain"))
    if not has_model:
        st.error("Select at least one model in the sidebar before chatting.")

    placeholder = (
        "Select a valid project folder in the sidebar first…"
        if not project_root_valid
        else "Ask the agent to explain, review, or modify code…"
    )
    prompt = st.chat_input(placeholder, disabled=not project_root_valid or not has_model)
    if not prompt:
        return

    if not st.session_state.get("api_key_ready"):
        st.error("Set an API key in the sidebar before chatting (or pick a provider that doesn't need one).")
        return

    if st.session_state.get("enhance_prompt_enabled"):
        candidate = _enhancer_model_and_key()
        if candidate is None:
            st.warning("The configured prompt-enhancer model's API key isn't set — sending as-is.")
            _submit_prompt(prompt, project_root, history)
        else:
            model, key = candidate
            with st.spinner(f"Enhancing prompt with {model}…"):
                try:
                    enhanced, was_enhanced = enhance_prompt(prompt, model, key)
                except Exception as exc:  # noqa: BLE001 - never let enhancement block sending
                    st.warning(f"Prompt enhancement failed ({exc}) — sending original prompt.")
                    _submit_prompt(prompt, project_root, history)
                else:
                    if not was_enhanced:
                        st.warning(
                            "Enhancement didn't produce a valid rewrite — sending your original prompt."
                        )
                        _submit_prompt(prompt, project_root, history)
                    else:
                        st.session_state.pending_enhancement = {
                            "original": prompt,
                            "enhanced": enhanced,
                            "model": model,
                        }
    else:
        _submit_prompt(prompt, project_root, history)

    st.rerun()
