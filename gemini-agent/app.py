"""Entrypoint: a lightweight, local Cowork-style coding agent for Gemini.

Run with: streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from src.changes.store import PendingChangeStore
from src.config import DEFAULT_PROVIDER, PROVIDERS
from src.persistence import load_exhausted_models
from src.ui.chat import render_chat
from src.ui.diff_view import render_pending_changes
from src.ui.sidebar import render_sidebar

st.set_page_config(page_title="Local Coding Agent", page_icon="🛠️", layout="wide")

st.session_state.setdefault("project_root", "")
st.session_state.setdefault("model", PROVIDERS[DEFAULT_PROVIDER]["models"][0])
st.session_state.setdefault("model_chain", [PROVIDERS[DEFAULT_PROVIDER]["models"][0]])
# Loaded from disk (not just {}) so a model that failed before a restart
# doesn't silently look "available" again on the next run.
st.session_state.setdefault("exhausted_models", load_exhausted_models())
st.session_state.setdefault("api_key_ready", False)
st.session_state.setdefault("project_summary", None)
st.session_state.setdefault("lc_messages", [])
st.session_state.setdefault("turn_error", None)
st.session_state.setdefault("turn_fallback_note", None)
st.session_state.setdefault("turn_compaction_note", None)
st.session_state.setdefault("turn_attempts", [])
st.session_state.setdefault("enhance_prompt_enabled", False)
st.session_state.setdefault("pending_enhancement", None)
st.session_state.setdefault("pending_store", PendingChangeStore())
st.session_state.setdefault("enable_phase_planning", False)
# task_id -> {"request_preview": str, "phases": [{"title","instructions","status"}], "current": int}
# Keyed per originating request so multiple large requests never collide.
st.session_state.setdefault("phase_tasks", {})
st.session_state.setdefault("active_phase_task_id", None)

st.title("🛠️ Local Coding Agent")
st.caption(
    "A lightweight, local Cowork-style assistant — Gemini or OpenRouter via LiteLLM, "
    "orchestrated with LangChain + LangGraph. All file edits are staged for your approval "
    "before anything touches disk."
)

render_sidebar()

chat_col, changes_col = st.columns([2, 1])
with chat_col:
    render_chat()
with changes_col:
    render_pending_changes()
