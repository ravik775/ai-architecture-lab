"""Sidebar: project root selection, model config, API key, project analysis."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.agent.llm import LiteLLMChatModel, is_capacity_error
from src.config import DEFAULT_PROVIDER, MAX_MODEL_CHAIN, PROVIDERS, get_api_key
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

    provider_names = list(PROVIDERS.keys())
    default_provider = st.session_state.get("provider", DEFAULT_PROVIDER)
    provider = st.sidebar.selectbox(
        "Provider",
        provider_names,
        index=provider_names.index(default_provider) if default_provider in provider_names else 0,
    )
    st.session_state.provider = provider
    provider_cfg = PROVIDERS[provider]

    exhausted = st.session_state.setdefault("exhausted_models", {})
    models = provider_cfg["models"]
    # Exhausted models are removed from what you can pick, not just skipped
    # at runtime - you restore one explicitly (below) when you want it back.
    available_models = [m for m in models if m not in exhausted]

    if not available_models:
        st.sidebar.error(
            "Every model for this provider is currently marked exhausted/unavailable. "
            "Restore one below, pick a different provider, or add a custom override."
        )
        st.session_state.model_chain = []
    else:
        chain_state_key = f"model_chain_selection_{provider}"
        default_selection = [
            m for m in st.session_state.get(chain_state_key, available_models[:1]) if m in available_models
        ]

        # A multiselect's own value lives under its `key` in session_state
        # and persists across reruns regardless of `options`/`default` -
        # filtering `available_models` alone doesn't clear an
        # already-selected model out of the widget's own bound state once
        # it's exhausted. Prune it here, before the widget reads that key.
        multiselect_key = f"model_multiselect_{provider}"
        if multiselect_key in st.session_state:
            st.session_state[multiselect_key] = [
                m for m in st.session_state[multiselect_key] if m in available_models
            ]

        selected = st.sidebar.multiselect(
            f"Models — priority order, up to {MAX_MODEL_CHAIN}",
            available_models,
            default=default_selection,
            max_selections=MAX_MODEL_CHAIN,
            key=multiselect_key,
            help=(
                "If the first model hits a rate limit or runs out of credits, the next one "
                "in this list is tried automatically, with no interruption. Exhausted models "
                "are removed from this list until you restore them below."
            ),
        )
        st.session_state[chain_state_key] = selected

        custom_model = st.sidebar.text_input(
            "Custom model override (optional, tried first)",
            placeholder=f"{models[0].split('/')[0]}/...",
            key=f"custom_model_{provider}",
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

    if not provider_cfg["api_key_env_vars"]:
        # e.g. Ollama - runs locally, nothing to authenticate.
        st.session_state.api_key = None
        st.session_state.api_key_ready = True
        st.sidebar.caption(
            "Runs locally — no API key needed. Make sure Ollama is running "
            f"and the model is pulled ({provider_cfg['key_url']})."
        )
    else:
        env_var_names = " / ".join(provider_cfg["api_key_env_vars"])
        env_key = get_api_key(provider_cfg["api_key_env_vars"])
        st.session_state.api_key = env_key
        st.session_state.api_key_ready = bool(env_key)
        if env_key:
            st.sidebar.caption(f"API key loaded from environment ({env_var_names}).")
        else:
            st.sidebar.error(
                f"{env_var_names} not set. Add it to `.env` in the project root "
                f"(gemini-agent/.env) — get a key at {provider_cfg['key_url']}, then restart the app."
            )

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
                with st.sidebar.status(f"Analyzing project… ({candidate})"):
                    llm = LiteLLMChatModel(model=candidate, api_key=st.session_state.api_key)
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
