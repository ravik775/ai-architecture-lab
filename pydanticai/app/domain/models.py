"""Pure domain models - no ORM, no framework types.

These are what flow through `application/` and `agent/`. Infrastructure
layers (SQLAlchemy rows, Open-Meteo JSON, PydanticAI tool results) all map
into/out of these at the boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class ProviderName(StrEnum):
    OPEN_METEO_FORECAST = "open-meteo-forecast"
    OPEN_METEO_METEOSWISS = "open-meteo-meteoswiss"


class CollectionType(StrEnum):
    ON_DEMAND = "on_demand"
    DAILY_BATCH = "daily_batch"


class LocationType(StrEnum):
    CITY = "city"
    STATION = "station"
    COORDINATES = "coordinates"


@dataclass(frozen=True, slots=True)
class WeatherObservation:
    """A single point-in-time weather reading for a precise coordinate."""

    latitude: float
    longitude: float
    observation_time_utc: datetime
    local_date: date
    temperature_c: float
    apparent_temperature_c: float
    humidity_percent: float
    precipitation_mm: float
    weather_code: int
    wind_speed_kmh: float
    wind_direction_deg: float
    provider: ProviderName
    model: str
    unit_system: str
    collection_type: CollectionType
    location_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConfiguredLocation:
    location_id: str
    location_name: str
    location_type: LocationType
    country_code: str
    country_name: str
    latitude: float
    longitude: float
    timezone: str
    provider_preference: str
    active: bool
    daily_collection_enabled: bool
    is_state_representative: bool
    state_code: str | None = None
    state_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Country:
    country_code: str
    country_name: str
    active: bool


@dataclass(frozen=True, slots=True)
class State:
    country_code: str
    state_code: str
    state_name: str
    active: bool
    representative_location_id: str | None = None


@dataclass(frozen=True, slots=True)
class DailyCollectionRun:
    job_id: str
    scheduled_time: datetime
    status: str
    total_location_count: int
    success_count: int
    failure_count: int
    start_time: datetime | None = None
    finish_time: datetime | None = None
    error_summary: list[str] | None = None
