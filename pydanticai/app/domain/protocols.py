"""Provider-neutral interfaces. Infrastructure implements these; application
services and agent tools depend only on these, never on a concrete provider.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from app.domain.models import WeatherObservation


class WeatherProvider(Protocol):
    """A source of weather data for a precise coordinate.

    Implementations must never represent an entire country/state - callers
    always pass a specific latitude/longitude.
    """

    async def get_current_weather(
        self,
        *,
        latitude: float,
        longitude: float,
        timezone: str,
        provider_preference: str = "open_meteo",
        location_id: str | None = None,
    ) -> WeatherObservation: ...

    async def get_daily_weather(
        self,
        *,
        latitude: float,
        longitude: float,
        timezone: str,
        target_date: date,
        provider_preference: str = "open_meteo",
        location_id: str | None = None,
    ) -> WeatherObservation: ...


class WeatherCache(Protocol):
    """Bounded, TTL-based cache. Single-process only - see architecture
    notes on the single-replica limitation of an in-memory cache."""

    async def get(self, key: str) -> WeatherObservation | None: ...

    async def set(self, key: str, value: WeatherObservation) -> None: ...
