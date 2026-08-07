from __future__ import annotations

from dataclasses import dataclass

from app.application.history_service import HistoryService
from app.application.location_service import LocationService
from app.application.weather_service import WeatherService


@dataclass
class AgentDeps:
    location_service: LocationService
    weather_service: WeatherService
    history_service: HistoryService
