"""UI data operations - thin adapters over the same `app.state.*` services
the REST API uses (in-process, no HTTP hop). Deliberately NiceGUI-free:
every function here returns plain data (dicts/lists), so it's testable
without a UI context and `pages.py` owns all DOM mutation. Each is wrapped
with the same `ui_operations_total`/`ui_operation_duration_seconds`
metrics the HTTP middleware records for API requests, and the services
they call already carry their own tracing/metrics (see `weather_service.py`,
`agent.py`) - so a UI action produces the same traces/metrics as the
equivalent API call.
"""
from __future__ import annotations

import functools
import logging
import time

from fastapi import FastAPI

from app.application.history_service import DateRangeTooLargeError
from app.domain.errors import (
    AgentTimeoutError,
    BatchAlreadyRunningError,
    InvalidCredentialsError,
    LocationNotFoundError,
    WeatherProviderError,
)
from app.observability.metrics import ui_operation_duration_seconds, ui_operations_total

logger = logging.getLogger(__name__)


def _instrumented_ui_op(name: str):
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            started = time.perf_counter()
            status = "success"
            try:
                return await fn(*args, **kwargs)
            except Exception:
                status = "error"
                raise
            finally:
                ui_operations_total.labels(operation=name, status=status).inc()
                ui_operation_duration_seconds.labels(operation=name).observe(time.perf_counter() - started)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Location dropdowns - all return {value: label} dicts (NiceGUI's ui.select
# option format).
# ---------------------------------------------------------------------------


@_instrumented_ui_op("load_countries")
async def fetch_countries(app: FastAPI) -> dict[str, str]:
    countries = await app.state.location_service.list_countries()
    return {c.country_code: f"{c.country_name} ({c.country_code})" for c in countries}


@_instrumented_ui_op("load_states")
async def fetch_states(app: FastAPI, country_code: str | None) -> dict[str, str]:
    if not country_code:
        return {}
    states = await app.state.location_service.list_states(country_code)
    return {s.state_code: f"{s.state_name} ({s.state_code})" for s in states}


@_instrumented_ui_op("load_locations")
async def fetch_locations(app: FastAPI, country_code: str | None, state_code: str | None) -> dict[str, str]:
    if not country_code:
        return {}
    locations = await app.state.location_service.list_locations(
        country_code=country_code, state_code=state_code or None
    )
    return {loc.location_id: loc.location_name for loc in locations}


@_instrumented_ui_op("load_all_locations")
async def fetch_all_locations(app: FastAPI) -> dict[str, str]:
    """Flat location list (all countries) - used by the History tab, which
    has no country/state cascade of its own."""
    locations = await app.state.location_service.list_locations()
    return {loc.location_id: f"{loc.location_name}, {loc.country_name}" for loc in locations}


# ---------------------------------------------------------------------------
# Current Weather tab
# ---------------------------------------------------------------------------


@_instrumented_ui_op("get_current_weather")
async def fetch_current_weather(app: FastAPI, location_id: str) -> dict:
    try:
        result, location = await app.state.weather_service.get_current_by_location_id(location_id)
    except LocationNotFoundError:
        return {"ok": False, "error": "Location not found or inactive."}
    except WeatherProviderError:
        return {"ok": False, "error": "The weather provider is temporarily unavailable. Please try again shortly."}

    obs = result.observation
    conditions = (
        f"### {location.location_name}, {location.country_name}\n\n"
        f"**{obs.temperature_c}°C** (feels like {obs.apparent_temperature_c}°C)\n\n"
        f"Humidity: {obs.humidity_percent}%  |  Wind: {obs.wind_speed_kmh} km/h  |  "
        f"Precipitation: {obs.precipitation_mm} mm"
    )
    if location.is_state_representative:
        conditions += (
            f"\n\n*Representative location for {location.state_name} - "
            "not an average for the whole state/province.*"
        )

    return {
        "ok": True,
        "conditions_md": conditions,
        "observation_time": obs.observation_time_utc.isoformat(),
        "provider_model": f"{obs.provider.value} / {obs.model}",
        "cache_status": "hit (served from cache)" if result.cache_hit else "miss (fetched live)",
    }


# ---------------------------------------------------------------------------
# Ask Weather Agent tab
# ---------------------------------------------------------------------------


@_instrumented_ui_op("ask_agent")
async def fetch_agent_answer(app: FastAPI, message: str, debug_mode: bool) -> dict:
    try:
        outcome = await app.state.agent_service.query(message)
    except AgentTimeoutError:
        return {"ok": False, "error": "The agent took too long to respond. Please try again."}
    except Exception:
        logger.exception("agent query failed")
        return {"ok": False, "error": "Something went wrong answering that. Please try again."}

    result = outcome.result
    resolved = "-"
    if result.resolved_location:
        loc = result.resolved_location
        resolved = f"{loc.location_name}, {loc.country_name}"
        if loc.state_name:
            resolved += f" ({loc.state_name})"
        if loc.is_state_representative:
            resolved += " - state representative"
    elif result.needs_clarification and result.clarification_options:
        resolved = "Ambiguous - candidates: " + ", ".join(o.location_name for o in result.clarification_options)

    weather = "-"
    if result.weather:
        w = result.weather
        weather = (
            f"{w.temperature_c}°C (feels like {w.apparent_temperature_c}°C), "
            f"humidity {w.humidity_percent}%, wind {w.wind_speed_kmh} km/h\n"
            f"Observed: {w.observation_time_utc}  |  {w.provider} / {w.model}"
        )

    debug = ""
    if debug_mode:
        debug = "Tool calls: " + (", ".join(outcome.tool_calls) if outcome.tool_calls else "(none)")

    return {
        "ok": True,
        "answer": result.answer,
        "resolved": resolved,
        "weather": weather,
        "duration": f"{outcome.duration_ms:.0f} ms",
        "debug": debug,
    }


# ---------------------------------------------------------------------------
# Weather History tab
# ---------------------------------------------------------------------------


@_instrumented_ui_op("get_history")
async def fetch_history(app: FastAPI, location_id: str | None, start_date: str, end_date: str) -> dict:
    if not location_id:
        return {"ok": False, "error": "Select a location first."}

    try:
        rows, total, _ = await app.state.history_service.list_history(
            location_id=location_id,
            start_date=start_date or None,
            end_date=end_date or None,
            page=1,
            page_size=100,
        )
    except DateRangeTooLargeError as exc:
        return {"ok": False, "error": str(exc)}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if not rows:
        return {"ok": True, "columns": [], "rows": [], "chart_dates": [], "chart_temps": [], "message": "No observations found for this range."}

    ordered = sorted(rows, key=lambda r: r.local_date)
    columns = [
        {"name": "date", "label": "Date", "field": "date", "align": "left"},
        {"name": "temperature_c", "label": "Temp (°C)", "field": "temperature_c"},
        {"name": "humidity_percent", "label": "Humidity (%)", "field": "humidity_percent"},
        {"name": "precipitation_mm", "label": "Precip (mm)", "field": "precipitation_mm"},
    ]
    table_rows = [
        {
            "date": r.local_date.isoformat(),
            "temperature_c": r.temperature_c,
            "humidity_percent": r.humidity_percent,
            "precipitation_mm": r.precipitation_mm,
        }
        for r in ordered
    ]
    return {
        "ok": True,
        "columns": columns,
        "rows": table_rows,
        "chart_dates": [r.local_date.isoformat() for r in ordered],
        "chart_temps": [r.temperature_c for r in ordered],
        "message": f"{total} observation(s) found.",
    }


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------


@_instrumented_ui_op("login")
async def fetch_login(app: FastAPI, username: str, password: str) -> dict:
    """Same JWT auth as `POST /v1/auth/login`, called in-process rather
    than over HTTP - this UI has no login *wall* (see pages.py's login
    page docstring), so this exists to make the existing JWT/RBAC
    capability reachable from a browser instead of only curl."""
    if not username or not password:
        return {"ok": False, "error": "Username and password are required."}
    try:
        token, expires_in, role = await app.state.auth_service.login(username=username, password=password)
    except InvalidCredentialsError:
        return {"ok": False, "error": "Invalid username or password."}
    return {"ok": True, "username": username, "role": role, "access_token": token, "expires_in": expires_in}


# ---------------------------------------------------------------------------
# Batch Status tab
# ---------------------------------------------------------------------------


def _format_run(run) -> str:
    if run is None:
        return "No collection runs recorded yet."
    lines = [
        f"**Job:** `{run.job_id}`",
        f"**Status:** {run.status}",
        f"**Scheduled:** {run.scheduled_time}",
        f"**Started:** {run.start_time or '-'}",
        f"**Finished:** {run.finish_time or '-'}",
        f"**Locations:** {run.total_location_count} total, "
        f"{run.success_count} succeeded, {run.failure_count} failed",
    ]
    return "\n\n".join(lines)


@_instrumented_ui_op("get_batch_status")
async def fetch_batch_status(app: FastAPI) -> str:
    async with app.state.db.session() as session:
        run = await app.state.job_repository.get_latest_run(session)
    return _format_run(run)


@_instrumented_ui_op("trigger_batch")
async def trigger_batch(app: FastAPI) -> dict:
    try:
        run = await app.state.batch_service.run_daily_collection(trigger_source="manual")
    except BatchAlreadyRunningError as exc:
        return {"ok": False, "error": f"A run is already in progress: `{exc.job_id}`"}
    except Exception:
        logger.exception("manual batch trigger failed")
        return {"ok": False, "error": "Failed to trigger the collection run. Check server logs."}
    return {"ok": True, "status_md": _format_run(run)}
