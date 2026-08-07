"""NiceGUI UI - a thin presentation layer over `app.state.*` services,
mounted into the existing FastAPI app in-process via `ui.run_with(app,
mount_path="/ui")`. All data operations live in `callbacks.py`; this module
owns layout and DOM wiring only.

Session state (login token, Correlation ID, Trace-checkbox preference)
lives in NiceGUI's `app.storage.user` - a server-side dict keyed by a
signed browser cookie (`SECURITY__UI_STORAGE_SECRET`). Imported as
`ng_app` to avoid colliding with the `app: FastAPI` parameter threaded
through every function below (this file's own `app` is always the FastAPI
instance, never the NiceGUI one).
"""
from __future__ import annotations

import time

from fastapi import FastAPI
from nicegui import app as ng_app, ui
from nicegui.elements.checkbox import Checkbox
from nicegui.elements.input import Input

from app.config.settings import Settings
from app.observability.correlation import correlation_scope, new_correlation_id
from app.ui.callbacks import (
    fetch_agent_answer,
    fetch_all_locations,
    fetch_batch_status,
    fetch_countries,
    fetch_current_weather,
    fetch_history,
    fetch_locations,
    fetch_login,
    fetch_states,
    trigger_batch,
)

EMPTY_CHART_OPTIONS = {
    "xAxis": {"type": "category", "data": []},
    "yAxis": {"type": "value", "name": "°C"},
    "series": [{"type": "line", "name": "Temperature", "data": []}],
}


def _current_auth() -> dict | None:
    """Reads the signed-in session (if any) from browser storage, clearing
    it out if the token has expired. Must be called from inside a page
    handler - `app.storage.user` requires an active client connection."""
    auth = ng_app.storage.user.get("auth")
    if auth and time.time() < auth.get("expires_at", 0):
        return auth
    if auth:
        ng_app.storage.user.pop("auth", None)
    return None


def _trace_kwargs(trace_checkbox: Checkbox) -> dict:
    """Only actually forces a trace when BOTH the checkbox is on AND a
    session is signed in - `correlation_scope` itself also guards on both
    being truthy, this is just the UI-side half of that same check."""
    if not trace_checkbox.value:
        return {}
    auth = _current_auth()
    if not auth:
        return {}
    return {"force_trace": True, "auth_token": auth["access_token"]}


def register_ui(app: FastAPI, settings: Settings) -> None:
    @ui.page("/")
    async def index() -> None:
        auth = _current_auth()

        with ui.row().classes("w-full items-center justify-between"):
            ui.markdown("# Weather Intelligence Agent")
            if auth:
                with ui.row().classes("items-center gap-2"):
                    ui.label(f"Signed in as {auth['username']} ({auth['role']})").classes("text-sm text-green-700")
                    ui.link("Log out", "/logout").classes("text-sm")
            else:
                ui.link("Log in", "/login").classes("text-sm")

        with ui.row().classes("w-full items-center gap-2"):
            ui.label("Correlation ID:").classes("font-medium")
            stored_correlation_id = ng_app.storage.user.get("correlation_id") or new_correlation_id()
            ng_app.storage.user["correlation_id"] = stored_correlation_id
            correlation_id_input = ui.input(value=stored_correlation_id).classes("flex-1 font-mono")
            correlation_id_input.tooltip(
                "Tags every trace/log line this session produces. Persisted for this "
                "browser session - edit it to something memorable, or click refresh "
                "for a new one."
            )

            def _persist_correlation_id() -> None:
                ng_app.storage.user["correlation_id"] = correlation_id_input.value

            correlation_id_input.on_value_change(_persist_correlation_id)

            def _new_correlation_id() -> None:
                correlation_id_input.set_value(new_correlation_id())
                _persist_correlation_id()

            ui.button(icon="refresh", on_click=_new_correlation_id).props("flat round dense").tooltip(
                "Generate a new correlation ID"
            )

            trace_checkbox = ui.checkbox(
                "Trace", value=bool(auth) and ng_app.storage.user.get("trace_enabled", False)
            )

            def _persist_trace_enabled() -> None:
                ng_app.storage.user["trace_enabled"] = trace_checkbox.value

            trace_checkbox.on_value_change(_persist_trace_enabled)
            if auth and auth["role"] == "trace_admin":
                trace_checkbox.tooltip(
                    "Forces the next action's trace to be captured regardless of "
                    "sampling (see README's Sampling section)."
                )
            else:
                trace_checkbox.disable()
                trace_checkbox.tooltip(
                    "Requires being signed in with the trace_admin role - see the "
                    "Log in link above."
                )

        with ui.tabs().classes("w-full") as tabs:
            tab_current = ui.tab("Current Weather")
            tab_agent = ui.tab("Ask Weather Agent")
            tab_history = ui.tab("Weather History")
            tab_batch = ui.tab("Batch Status")

        with ui.tab_panels(tabs, value=tab_current).classes("w-full"):
            with ui.tab_panel(tab_current):
                await _build_current_weather_tab(app, correlation_id_input, trace_checkbox)
            with ui.tab_panel(tab_agent):
                await _build_agent_tab(app, settings, correlation_id_input, trace_checkbox)
            with ui.tab_panel(tab_history):
                await _build_history_tab(app, correlation_id_input, trace_checkbox)
            with ui.tab_panel(tab_batch):
                await _build_batch_tab(app, settings, correlation_id_input, trace_checkbox)

    @ui.page("/logout")
    async def logout_page() -> None:
        ng_app.storage.user.pop("auth", None)
        ui.navigate.to("/")

    @ui.page("/login")
    async def login_page() -> None:
        """Authenticates against the same JWT auth the REST API uses
        (`POST /v1/auth/login`, called in-process - see `fetch_login`). On
        success the token is stored in `app.storage.user` (this browser's
        signed session cookie) and the user is sent back to the weather
        app - see `_current_auth`/`_trace_kwargs` for how the rest of the
        UI reads it back out. Deliberately not a gate: every other page
        works without logging in, matching this app's single-user
        local-demo scope (see README's Authentication section) - logging
        in only unlocks the "Trace" checkbox on the home page (the
        `force_trace` sampling override, which requires a `trace_admin`
        token)."""
        with ui.row().classes("w-full items-center justify-between"):
            ui.markdown("# Log in")
            ui.link("← Back to home", "/")

        ui.label(
            "This UI itself doesn't require login. Logging in unlocks the "
            "\"Trace\" checkbox on the home page (force_trace override) - "
            "see README."
        ).classes("text-sm text-gray-500 max-w-lg")

        with ui.column().classes("gap-2 max-w-sm"):
            username_input = ui.input(label="Username").classes("w-full")
            password_input = ui.input(label="Password", password=True, password_toggle_button=True).classes(
                "w-full"
            )
            login_button = ui.button("Log in")
            error_label = ui.label().classes("text-red-600")

            async def do_login() -> None:
                login_button.disable()
                error_label.set_text("")
                try:
                    result = await fetch_login(app, username_input.value, password_input.value)
                finally:
                    login_button.enable()

                if not result["ok"]:
                    error_label.set_text(result["error"])
                    return

                ng_app.storage.user["auth"] = {
                    "access_token": result["access_token"],
                    "username": result["username"],
                    "role": result["role"],
                    "expires_at": time.time() + result["expires_in"],
                }
                ui.notify(f"Signed in as {result['username']} ({result['role']}).", type="positive")
                ui.navigate.to("/")

            login_button.on_click(do_login)
            password_input.on("keydown.enter", do_login)

    ui.run_with(
        app,
        mount_path="/ui",
        title="Weather Intelligence Agent",
        show_welcome_message=False,
        storage_secret=settings.security.ui_storage_secret,
    )


async def _build_current_weather_tab(
    app: FastAPI, correlation_id_input: Input, trace_checkbox: Checkbox
) -> None:
    with ui.row().classes("w-full"):
        country_select = ui.select({}, label="Country").classes("flex-1")
        state_select = ui.select({}, label="State / Province").classes("flex-1")
        location_select = ui.select({}, label="Location").classes("flex-1")
    get_weather_btn = ui.button("Get Weather")
    conditions_md = ui.markdown()
    with ui.row().classes("w-full"):
        obs_time_input = ui.input(label="Observation Time (UTC)").props("readonly").classes("flex-1")
        provider_input = ui.input(label="Provider / Model").props("readonly").classes("flex-1")
        cache_input = ui.input(label="Cache Status").props("readonly").classes("flex-1")

    async def on_country_change() -> None:
        country_code = country_select.value
        with correlation_scope(correlation_id_input.value, "ui.load_states_and_locations"):
            state_select.set_options(await fetch_states(app, country_code), value=None)
            location_select.set_options(await fetch_locations(app, country_code, None), value=None)

    async def on_state_change() -> None:
        with correlation_scope(correlation_id_input.value, "ui.load_locations"):
            location_select.set_options(
                await fetch_locations(app, country_select.value, state_select.value), value=None
            )

    async def on_get_weather() -> None:
        location_id = location_select.value
        if not location_id:
            ui.notify("Select a location first.", type="warning")
            return
        get_weather_btn.disable()
        conditions_md.set_content("Loading...")
        try:
            with correlation_scope(
                correlation_id_input.value, "ui.get_current_weather", **_trace_kwargs(trace_checkbox)
            ):
                result = await fetch_current_weather(app, location_id)
        finally:
            get_weather_btn.enable()

        if not result["ok"]:
            conditions_md.set_content(result["error"])
            obs_time_input.value = ""
            provider_input.value = ""
            cache_input.value = ""
            return
        conditions_md.set_content(result["conditions_md"])
        obs_time_input.value = result["observation_time"]
        provider_input.value = result["provider_model"]
        cache_input.value = result["cache_status"]

    country_select.on_value_change(on_country_change)
    state_select.on_value_change(on_state_change)
    get_weather_btn.on_click(on_get_weather)

    with correlation_scope(correlation_id_input.value, "ui.load_countries"):
        country_select.set_options(await fetch_countries(app))


async def _build_agent_tab(
    app: FastAPI, settings: Settings, correlation_id_input: Input, trace_checkbox: Checkbox
) -> None:
    debug_checkbox = ui.checkbox("Debug mode (show tool calls)", value=settings.ui.debug_mode)
    question_input = ui.input(
        label="Ask a weather question", placeholder="Should I carry an umbrella in Hyderabad today?"
    ).classes("w-full")
    ask_btn = ui.button("Ask")
    answer_md = ui.markdown()
    with ui.row().classes("w-full"):
        resolved_input = ui.input(label="Resolved Location").props("readonly").classes("flex-1")
        weather_input = ui.textarea(label="Weather Details").props("readonly").classes("flex-1")
        duration_input = ui.input(label="Agent Duration").props("readonly").classes("flex-1")
    debug_md = ui.markdown()

    async def on_ask() -> None:
        message = (question_input.value or "").strip()
        if not message:
            ui.notify("Ask a weather question first.", type="warning")
            return
        ask_btn.disable()
        answer_md.set_content("Thinking...")
        try:
            with correlation_scope(correlation_id_input.value, "ui.ask_agent", **_trace_kwargs(trace_checkbox)):
                result = await fetch_agent_answer(app, message, debug_checkbox.value)
        finally:
            ask_btn.enable()

        if not result["ok"]:
            answer_md.set_content(result["error"])
            return
        answer_md.set_content(result["answer"])
        resolved_input.value = result["resolved"]
        weather_input.value = result["weather"]
        duration_input.value = result["duration"]
        debug_md.set_content(result["debug"])

    ask_btn.on_click(on_ask)


async def _build_history_tab(app: FastAPI, correlation_id_input: Input, trace_checkbox: Checkbox) -> None:
    with ui.row().classes("w-full"):
        location_select = ui.select({}, label="Location").classes("flex-1")
        start_date_input = ui.input(label="Start Date (YYYY-MM-DD)").classes("flex-1")
        end_date_input = ui.input(label="End Date (YYYY-MM-DD)").classes("flex-1")
    history_btn = ui.button("Load History")
    status_md = ui.markdown()
    table = ui.table(columns=[], rows=[], row_key="date").classes("w-full")
    chart = ui.echart(dict(EMPTY_CHART_OPTIONS)).classes("w-full")

    async def on_load_history() -> None:
        location_id = location_select.value
        history_btn.disable()
        try:
            with correlation_scope(correlation_id_input.value, "ui.get_history", **_trace_kwargs(trace_checkbox)):
                result = await fetch_history(app, location_id, start_date_input.value, end_date_input.value)
        finally:
            history_btn.enable()

        if not result["ok"]:
            status_md.set_content(result["error"])
            return

        table.columns = result["columns"]
        table.rows = result["rows"]
        table.update()

        chart.options["xAxis"]["data"] = result["chart_dates"]
        chart.options["series"][0]["data"] = result["chart_temps"]
        chart.update()

        status_md.set_content(result["message"])

    history_btn.on_click(on_load_history)

    with correlation_scope(correlation_id_input.value, "ui.load_all_locations"):
        location_select.set_options(await fetch_all_locations(app))


async def _build_batch_tab(
    app: FastAPI, settings: Settings, correlation_id_input: Input, trace_checkbox: Checkbox
) -> None:
    status_md = ui.markdown()
    refresh_btn = ui.button("Refresh Status")

    async def on_refresh() -> None:
        with correlation_scope(correlation_id_input.value, "ui.get_batch_status", **_trace_kwargs(trace_checkbox)):
            status_md.set_content(await fetch_batch_status(app))

    refresh_btn.on_click(on_refresh)

    if settings.scheduler.manual_trigger_enabled and settings.ui.batch_manual_trigger_visible:
        trigger_btn = ui.button("Trigger Collection Now", color="negative")

        async def on_trigger() -> None:
            trigger_btn.disable()
            status_md.set_content("Triggering collection run...")
            try:
                with correlation_scope(
                    correlation_id_input.value, "ui.trigger_batch", **_trace_kwargs(trace_checkbox)
                ):
                    result = await trigger_batch(app)
            finally:
                trigger_btn.enable()
            status_md.set_content(result["status_md"] if result["ok"] else result["error"])

        trigger_btn.on_click(on_trigger)

    with correlation_scope(correlation_id_input.value, "ui.get_batch_status"):
        status_md.set_content(await fetch_batch_status(app))
