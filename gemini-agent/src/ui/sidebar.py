"""Sidebar: project root selection, model config, API key, project analysis."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.agent.llm import LiteLLMChatModel, is_capacity_error
from src.config import (
    ALL_MODELS,
    MAX_MODEL_CHAIN,
    find_provider_for_model,
    resolve_api_key_for_model,
)
from src.persistence import save_exhausted_models
from src.project.indexer import analyze_project


def _browse_folder() -> str | None:
    """Open a native OS folder picker. Returns None if unavailable (headless)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory()
        root.destroy()
        return path or None
    except Exception:
        return None


def render_sidebar() -> None:
    st.sidebar.header("Project")

    current_path = st.session_state.get("project_root", "")
    col1, col2 = st.sidebar.columns([3, 1])
    new_path = col1.text_input(
        "Project root",
        value=current_path,
        label_visibility="collapsed",
        placeholder="Path to project folder",
    )
    if col2.button("Browse…"):
        picked = _browse_folder()
        if picked:
            new_path = picked
        else:
            st.sidebar.warning("No folder dialog available here — enter a path manually.")

    if new_path != current_path:
        st.session_state.project_root = new_path
        st.session_state.project_summary = None

    project_root_valid = bool(new_path) and Path(new_path).is_dir()
    if new_path:
        if project_root_valid:
            # Backticks force a markdown code span, so path segments with
            # underscores etc. render literally instead of being parsed as
            # markdown emphasis syntax (which silently eats backslashes).
            st.sidebar.success(f"Using: `{Path(new_path).resolve()}`")
        else:
            st.sidebar.error("Not a valid directory.")

    st.sidebar.divider()
    st.sidebar.header("Model")

    exhausted = st.session_state.setdefault("exhausted_models", {})
    # Exhausted models are removed from what you can pick, not just skipped
    # at runtime - you restore one explicitly (below) when you want it back.
    available_models = [m for m in ALL_MODELS if m not in exhausted]

    if not available_models:
        st.sidebar.error(
            "Every configured model is currently marked exhausted/unavailable. "
            "Restore one below, or add a custom override."
        )
        st.session_state.model_chain = []
    else:
        chain_state_key = "model_chain_selection"
        default_selection = [
            m for m in st.session_state.get(chain_state_key, available_models[:1]) if m in available_models
        ]

        # A multiselect's own value lives under its `key` in session_state
        # and persists across reruns regardless of `options`/`default` -
        # filtering `available_models` alone doesn't clear an
        # already-selected model out of the widget's own bound state once
        # it's exhausted. Prune it here, before the widget reads that key.
        # Streamlit warns (harmlessly, but noisily) if `default=` is passed
        # once a widget's key already has a session_state value, so only
        # pass `default=` the first time this key is ever created.
        multiselect_key = "model_multiselect_global"
        key_already_set = multiselect_key in st.session_state
        if key_already_set:
            st.session_state[multiselect_key] = [
                m for m in st.session_state[multiselect_key] if m in available_models
            ]

        multiselect_kwargs: dict = {
            "options": available_models,
            "max_selections": MAX_MODEL_CHAIN,
            "key": multiselect_key,
            "help": (
                "Pick up to 4 models from any provider, in priority order — mix providers "
                "freely, each resolves its own API key. If one hits a rate limit or runs out "
                "of credits, the next is tried automatically. Exhausted models are removed "
                "from this list until you restore them below."
            ),
        }
        if not key_already_set:
            multiselect_kwargs["default"] = default_selection

        selected = st.sidebar.multiselect(
            f"Models — priority order, up to {MAX_MODEL_CHAIN} (any provider)",
            **multiselect_kwargs,
        )
        st.session_state[chain_state_key] = selected

        custom_model = st.sidebar.text_input(
            "Custom model override (optional, tried first)",
            placeholder="openrouter/... or huggingface/... or ollama_chat/...",
            key="custom_model_global",
        )

        chain = ([custom_model.strip()] if custom_model.strip() else []) + selected
        seen: set[str] = set()
        chain = [m for m in chain if not (m in seen or seen.add(m))][:MAX_MODEL_CHAIN]
        st.session_state.model_chain = chain
        st.session_state.model = chain[0] if chain else available_models[0]
        if not chain:
            st.sidebar.error("Select at least one model before sending a request.")

    if exhausted:
        with st.sidebar.expander(f"Exhausted / unavailable models ({len(exhausted)})", expanded=False):
            for model_name, err in list(exhausted.items()):
                st.caption(f"**{model_name}**")
                st.code(err[:300], language=None)
                if st.button("Restore to available", key=f"restore-{model_name}"):
                    del exhausted[model_name]
                    save_exhausted_models(exhausted)
                    st.rerun()
            if st.button("Reset exhausted list", key="reset_exhausted"):
                st.session_state.exhausted_models = {}
                save_exhausted_models({})
                st.rerun()

    # Each selected model resolves its own key against whichever provider it
    # belongs to - show status per distinct provider actually represented in
    # the chain, not one single "selected provider" (there isn't one anymore).
    st.sidebar.caption("API keys for your selected models:")
    chain_for_status = st.session_state.get("model_chain") or []
    shown_providers: set[str] = set()
    any_model_ready = False
    for m in chain_for_status:
        found = find_provider_for_model(m)
        if found is None:
            st.sidebar.caption(f"⚠️ `{m}`: unrecognized provider prefix.")
            continue
        pname, pcfg = found
        if pname in shown_providers:
            continue
        shown_providers.add(pname)
        if not pcfg["api_key_env_vars"]:
            st.sidebar.caption(f"✅ {pname}: runs locally, no key needed.")
            any_model_ready = True
        else:
            env_var_names = " / ".join(pcfg["api_key_env_vars"])
            if resolve_api_key_for_model(m):
                st.sidebar.caption(f"✅ {pname}: key loaded ({env_var_names}).")
                any_model_ready = True
            else:
                st.sidebar.caption(
                    f"❌ {pname}: {env_var_names} not set — get one at {pcfg['key_url']}."
                )
    st.session_state.api_key_ready = bool(chain_for_status) and any_model_ready

    st.sidebar.divider()
    st.sidebar.header("Analysis")

    if st.sidebar.button("Analyze project", disabled=not project_root_valid):
        if not st.session_state.get("api_key_ready"):
            st.sidebar.error("Set an API key first.")
        elif not st.session_state.get("model_chain"):
            st.sidebar.error("Select at least one model first.")
        else:
            exhausted = st.session_state.setdefault("exhausted_models", {})
            attempt_chain = [m for m in st.session_state.model_chain if m not in exhausted] or st.session_state.model_chain
            last_exc: Exception | None = None
            for candidate in attempt_chain:
                candidate_key = resolve_api_key_for_model(candidate)
                found = find_provider_for_model(candidate)
                if found and found[1]["api_key_env_vars"] and not candidate_key:
                    continue  # no key for this one - skip straight to the next candidate
                with st.sidebar.status(f"Analyzing project… ({candidate})"):
                    llm = LiteLLMChatModel(model=candidate, api_key=candidate_key)
                    try:
                        st.session_state.project_summary = analyze_project(Path(new_path), llm)
                        last_exc = None
                        break
                    except Exception as exc:  # noqa: BLE001 - surface any provider/network error
                        last_exc = exc
                        if is_capacity_error(exc):
                            exhausted[candidate] = str(exc)
                            save_exhausted_models(exhausted)
                            continue
                        break
            if last_exc is not None:
                st.sidebar.error(f"Analysis failed: {last_exc}")

    if st.session_state.get("project_summary"):
        with st.sidebar.expander("Project summary", expanded=True):
            st.markdown(st.session_state.project_summary)

    store = st.session_state.get("pending_store")
    pending_count = len([c for c in store.changes.values() if c.status == "pending"]) if store else 0
    if pending_count:
        st.sidebar.info(f"{pending_count} change(s) awaiting review")
