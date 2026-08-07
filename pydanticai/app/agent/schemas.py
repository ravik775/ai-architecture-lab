"""The agent's validated Pydantic result model - what PydanticAI is
required to produce as structured output on every run."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LocationSummary(BaseModel):
    location_id: str
    location_name: str
    country_name: str
    state_name: str | None = None
    is_state_representative: bool = False


class WeatherSummary(BaseModel):
    temperature_c: float
    apparent_temperature_c: float
    humidity_percent: float
    precipitation_mm: float
    weather_code: int
    wind_speed_kmh: float
    wind_direction_deg: float
    observation_time_utc: str
    provider: str
    model: str


class AgentQueryResult(BaseModel):
    answer: str = Field(description="Concise natural-language answer to the user's question.")
    resolved_location: LocationSummary | None = None
    weather: WeatherSummary | None = None
    used_representative_location: bool = Field(
        default=False,
        description="True when the weather shown is for a state/province representative city, not the exact place asked about.",
    )
    representative_disclaimer: str | None = None
    needs_clarification: bool = Field(
        default=False, description="True when the location was ambiguous or unsupported and the user must pick."
    )
    clarification_options: list[LocationSummary] = Field(default_factory=list)
