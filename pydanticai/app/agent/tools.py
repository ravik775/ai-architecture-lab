"""Typed agent tools. Every tool calls an `application/` service directly -
never a REST endpoint, never a repository. This is the ONLY way the agent
touches location/weather facts, which is what makes "never fabricate a
location or weather value" enforceable: the model has no other data path.
"""
from __future__ import annotations

import functools
import time
from datetime import date
from typing import Any

from pydantic_ai import RunContext

from app.agent.deps import AgentDeps
from app.application.history_service import DateRangeTooLargeError
from app.application.weather_service import WeatherResult
from app.domain.errors import LocationNotFoundError, WeatherProviderError, WeatherProviderTimeoutError
from app.infrastructure.database.models import ConfiguredLocationRow, WeatherObservationRow
from app.observability.metrics import tool_call_duration_seconds, tool_calls_total


def _instrumented(name: str):
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            started = time.perf_counter()
            status = "success"
            try:
                return await fn(*args, **kwargs)
            except Exception:
                status = "failure"
                raise
            finally:
                tool_calls_total.labels(tool_name=name, status=status).inc()
                tool_call_duration_seconds.labels(tool_name=name).observe(time.perf_counter() - started)

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator


def _location_summary(row: ConfiguredLocationRow) -> dict[str, Any]:
    return {
        "location_id": row.location_id,
        "location_name": row.location_name,
        "country_code": row.country_code,
        "country_name": row.country_name,
        "state_code": row.state_code,
        "state_name": row.state_name,
        "is_state_representative": row.is_state_representative,
    }


def _weather_summary(result: WeatherResult) -> dict[str, Any]:
    obs = result.observation
    return {
        "temperature_c": obs.temperature_c,
        "apparent_temperature_c": obs.apparent_temperature_c,
        "humidity_percent": obs.humidity_percent,
        "precipitation_mm": obs.precipitation_mm,
        "weather_code": obs.weather_code,
        "wind_speed_kmh": obs.wind_speed_kmh,
        "wind_direction_deg": obs.wind_direction_deg,
        "observation_time_utc": obs.observation_time_utc.isoformat(),
        "provider": obs.provider.value,
        "model": obs.model,
        "cache_status": "hit" if result.cache_hit else "miss",
    }


def _history_row_summary(row: WeatherObservationRow) -> dict[str, Any]:
    return {
        "local_date": row.local_date.isoformat(),
        "temperature_c": row.temperature_c,
        "apparent_temperature_c": row.apparent_temperature_c,
        "humidity_percent": row.humidity_percent,
        "precipitation_mm": row.precipitation_mm,
        "weather_code": row.weather_code,
        "wind_speed_kmh": row.wind_speed_kmh,
        "provider": row.provider,
    }


@_instrumented("list_supported_countries")
async def list_supported_countries(ctx: RunContext[AgentDeps]) -> list[dict[str, Any]]:
    """List every country the weather agent has configured locations for."""
    countries = await ctx.deps.location_service.list_countries()
    return [{"country_code": c.country_code, "country_name": c.country_name} for c in countries]


@_instrumented("list_supported_states")
async def list_supported_states(ctx: RunContext[AgentDeps], country_code: str) -> list[dict[str, Any]]:
    """List supported states/provinces for a country (ISO 3166-1 alpha-2 code, e.g. 'IN', 'US', 'CH')."""
    states = await ctx.deps.location_service.list_states(country_code.upper())
    return [
        {
            "state_code": s.state_code,
            "state_name": s.state_name,
            "has_representative": s.representative_location_id is not None,
        }
        for s in states
    ]


@_instrumented("list_supported_locations")
async def list_supported_locations(
    ctx: RunContext[AgentDeps], country_code: str | None = None, state_code: str | None = None
) -> list[dict[str, Any]]:
    """List configured locations, optionally filtered by country_code and/or state_code."""
    locations = await ctx.deps.location_service.list_locations(
        country_code=country_code.upper() if country_code else None,
        state_code=state_code.upper() if state_code else None,
    )
    return [_location_summary(loc) for loc in locations]


@_instrumented("resolve_supported_location")
async def resolve_supported_location(ctx: RunContext[AgentDeps], query: str) -> dict[str, Any]:
    """Resolve a free-text place name (e.g. 'Hyderabad', 'zurich') to a configured location_id.

    Returns {"resolved": true, "location": {...}} on an unambiguous match, or
    {"resolved": false, "candidates": [...]} when ambiguous or unsupported - a
    candidates list may be empty, meaning nothing supported matches at all.
    NEVER invent a location_id that didn't come from this tool or
    list_supported_locations.
    """
    matches = await ctx.deps.location_service.search_locations_by_name(query, limit=5)
    if len(matches) == 1:
        return {"resolved": True, "location": _location_summary(matches[0])}
    return {"resolved": False, "candidates": [_location_summary(m) for m in matches]}


@_instrumented("get_current_weather")
async def get_current_weather(ctx: RunContext[AgentDeps], location_id: str) -> dict[str, Any]:
    """Get current weather for a configured location_id (obtained from
    resolve_supported_location or list_supported_locations - never a raw
    city name). Returns an "error" field instead of raising when the
    provider is unavailable or times out - report that honestly, never
    invent a plausible-looking reading."""
    try:
        result, location = await ctx.deps.weather_service.get_current_by_location_id(location_id)
    except LocationNotFoundError:
        return {"error": "location_not_found", "location_id": location_id}
    except WeatherProviderTimeoutError:
        return {"error": "provider_timeout", "location_id": location_id}
    except WeatherProviderError as exc:
        return {"error": "provider_unavailable", "location_id": location_id, "detail": str(exc)[:200]}

    return {"location": _location_summary(location), "weather": _weather_summary(result)}


@_instrumented("get_weather_history")
async def get_weather_history(
    ctx: RunContext[AgentDeps], location_id: str, start_date: date, end_date: date
) -> dict[str, Any]:
    """Get historical daily weather observations for a configured location
    between start_date and end_date inclusive (bounded range)."""
    try:
        rows, total, _ = await ctx.deps.history_service.list_history(
            location_id=location_id, start_date=start_date, end_date=end_date, page=1, page_size=100
        )
    except DateRangeTooLargeError as exc:
        return {"error": "date_range_too_large", "detail": str(exc)}
    return {"total": total, "observations": [_history_row_summary(r) for r in rows]}


AGENT_TOOLS = [
    list_supported_countries,
    list_supported_states,
    list_supported_locations,
    resolve_supported_location,
    get_current_weather,
    get_weather_history,
]
