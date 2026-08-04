"""Pending-changes panel: per-file diffs with approve/reject/apply controls."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.changes.store import PendingChangeStore

_ICONS = {"create": "➕", "modify": "✏️", "delete": "🗑️"}

# Matches the chat panel's history height, so both side-by-side panes scroll
# independently within their own bounded box - same as the native sidebar -
# instead of growing the whole page and scrolling together with chat.
PANEL_HEIGHT = 560


def render_pending_changes() -> None:
    store: PendingChangeStore = st.session_state.pending_store
    visible = [c for c in store.changes.values() if c.status in ("pending", "approved")]

    # st.container(height=...) has no native resize handle - this CSS adds a
    # drag-to-resize handle on the bottom edge (like a <textarea>), targeting
    # only this container via the `st-key-*` class Streamlit assigns to
    # elements given a `key=`.
    st.markdown(
        """<style>
        .st-key-pending_changes_panel {
            resize: vertical;
            overflow: auto !important;
            min-height: 200px;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    panel = st.container(height=PANEL_HEIGHT, border=True, key="pending_changes_panel")
    with panel:
        st.subheader(f"Pending changes ({len(visible)})")

        if not visible:
            st.caption("No proposed changes yet. Ask the agent to modify or create a file.")
            return

        for change in visible:
            icon = _ICONS.get(change.action, "•")
            label = f"{icon} {change.path}"
            if change.status == "approved":
                label += "  ✅"
            with st.expander(label, expanded=False):
                if change.description:
                    st.caption(change.description)
                st.code(change.diff(), language="diff")
                col1, col2 = st.columns(2)
                if col1.button(
                    "Approve", key=f"approve-{change.path}", disabled=change.status == "approved"
                ):
                    store.approve(change.path)
                    st.rerun()
                if col2.button("Reject", key=f"reject-{change.path}"):
                    store.reject(change.path)
                    st.rerun()

        st.divider()
        col1, col2, col3 = st.columns(3)
        if col1.button("Approve all"):
            store.approve_all()
            st.rerun()
        if col2.button("Apply approved", type="primary"):
            project_root = st.session_state.get("project_root")
            if not project_root:
                st.error("No project root selected.")
            else:
                applied = store.apply_approved(Path(project_root))
                store.clear_resolved()
                if applied:
                    st.success(f"Applied: {', '.join(applied)}")
                else:
                    st.info("No approved changes to apply.")
                st.rerun()
        if col3.button("Clear rejected"):
            store.clear_resolved()
            st.rerun()
