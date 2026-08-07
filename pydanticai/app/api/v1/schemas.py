"""Pydantic v2 request/response contracts for the v1 REST API.

These are API-layer DTOs, deliberately separate from `app.domain.models`
and the SQLAlchemy rows - the wire format is allowed to diverge from
internal representations without forcing a domain change.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import CollectionType, ProviderName
from app.infrastructure.database.models import (
    ConfiguredLocationRow,
    CountryRow,
    StateRow,
    WeatherObservationRow,
)
from app.infrastructure.database.utils import as_utc


class CountryOut(BaseModel):
    country_code: str
    country_name: str

    @classmethod
    def from_row(cls, row: CountryRow) -> "CountryOut":
        return cls(country_code=row.country_code, country_name=row.country_name)


class StateOut(BaseModel):
    country_code: str
    state_code: str
    state_name: str
    has_representative: bool

    @classmethod
    def from_row(cls, row: StateRow) -> "StateOut":
        return cls(
            country_code=row.country_code,
            state_code=row.state_code,
            state_name=row.state_name,
            has_representative=row.representative_location_id is not None,
        )


class LocationOut(BaseModel):
    location_id: str
    location_name: str
    location_type: str
    country_code: str
    country_name: str
    state_code: str | None
    state_name: str | None
    latitude: float
    longitude: float
    timezone: str
    provider_preference: str
    active: bool
    daily_collection_enabled: bool
    is_state_representative: bool

    @classmethod
    def from_row(cls, row: ConfiguredLocationRow) -> "LocationOut":
        return cls(
            location_id=row.location_id,
            location_name=row.location_name,
            location_type=row.location_type,
            country_code=row.country_code,
            country_name=row.country_name,
            state_code=row.state_code,
            state_name=row.state_name,
            latitude=row.latitude,
            longitude=row.longitude,
            timezone=row.timezone,
            provider_preference=row.provider_preference,
            active=row.active,
            daily_collection_enabled=row.daily_collection_enabled,
            is_state_representative=row.is_state_representative,
        )


class WeatherObservationOut(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

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


class CurrentWeatherResponse(BaseModel):
    location: LocationOut | None = None
    weather: WeatherObservationOut
    cache_status: Literal["hit", "miss"]
    latency_ms: float = Field(..., description="Service-observed latency for this request, in milliseconds.")


class StateWeatherResponse(BaseModel):
    representative_location: LocationOut | None = None
    weather: WeatherObservationOut | None = None
    cache_status: Literal["hit", "miss"] | None = None
    disclaimer: str | None = None
    message: str | None = None
    supported_locations: list[LocationOut] | None = None


class HistoryObservationOut(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    location_id: str
    observation_date: date
    observation_timestamp_utc: datetime
    local_date: date
    temperature_c: float
    apparent_temperature_c: float
    humidity_percent: float
    precipitation_mm: float
    weather_code: int
    wind_speed_kmh: float
    wind_direction_deg: float
    provider: str
    model: str
    unit_system: str
    collection_type: str

    @classmethod
    def from_row(cls, row: WeatherObservationRow) -> "HistoryObservationOut":
        return cls(
            location_id=row.location_id,
            observation_date=row.observation_date,
            observation_timestamp_utc=as_utc(row.observation_timestamp_utc),
            local_date=row.local_date,
            temperature_c=row.temperature_c,
            apparent_temperature_c=row.apparent_temperature_c,
            humidity_percent=row.humidity_percent,
            precipitation_mm=row.precipitation_mm,
            weather_code=row.weather_code,
            wind_speed_kmh=row.wind_speed_kmh,
            wind_direction_deg=row.wind_direction_deg,
            provider=row.provider,
            model=row.model,
            unit_system=row.unit_system,
            collection_type=row.collection_type,
        )


class HistoryResponse(BaseModel):
    items: list[HistoryObservationOut]
    total: int
    page: int
    page_size: int
    total_pages: int
