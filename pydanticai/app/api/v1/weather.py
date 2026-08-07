from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_location_service, get_settings_dep, get_weather_service
from app.api.v1.schemas import CurrentWeatherResponse, LocationOut, StateWeatherResponse, WeatherObservationOut
from app.application.location_service import LocationService
from app.application.weather_service import WeatherService
from app.config.settings import Settings
from app.domain.errors import LocationNotFoundError, WeatherProviderError

router = APIRouter(prefix="/v1/weather", tags=["weather"])


def _validate_timezone(timezone: str) -> None:
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown IANA timezone: {timezone!r}") from exc


@router.get("/current", response_model=CurrentWeatherResponse)
async def get_current_weather(
    location_id: str | None = Query(None),
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
    timezone: str | None = Query(None),
    weather_service: WeatherService = Depends(get_weather_service),
    settings: Settings = Depends(get_settings_dep),
) -> CurrentWeatherResponse:
    if location_id:
        try:
            result, location = await weather_service.get_current_by_location_id(location_id)
        except LocationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Location not found or inactive") from exc
        except WeatherProviderError as exc:
            raise HTTPException(status_code=502, detail="Weather provider unavailable") from exc
        return CurrentWeatherResponse(
            location=LocationOut.from_row(location),
            weather=WeatherObservationOut.model_validate(result.observation, from_attributes=True),
            cache_status="hit" if result.cache_hit else "miss",
            latency_ms=round(result.latency_ms, 2),
        )

    if latitude is not None and longitude is not None and timezone is not None:
        if not settings.security.allow_direct_coordinates:
            raise HTTPException(status_code=403, detail="Direct-coordinate weather lookups are disabled")
        _validate_timezone(timezone)
        try:
            result = await weather_service.get_current_by_coordinates(
                latitude=latitude, longitude=longitude, timezone=timezone
            )
        except WeatherProviderError as exc:
            raise HTTPException(status_code=502, detail="Weather provider unavailable") from exc
        return CurrentWeatherResponse(
            location=None,
            weather=WeatherObservationOut.model_validate(result.observation, from_attributes=True),
            cache_status="hit" if result.cache_hit else "miss",
            latency_ms=round(result.latency_ms, 2),
        )

    raise HTTPException(
        status_code=400,
        detail="Provide either location_id, or latitude+longitude+timezone",
    )


@router.get("/current/state", response_model=StateWeatherResponse)
async def get_state_representative_weather(
    country_code: str = Query(..., min_length=2, max_length=2),
    state_code: str = Query(..., min_length=1, max_length=10),
    weather_service: WeatherService = Depends(get_weather_service),
    location_service: LocationService = Depends(get_location_service),
) -> StateWeatherResponse:
    country_code = country_code.upper()
    state_code = state_code.upper()

    representative = await location_service.get_representative_location(
        country_code=country_code, state_code=state_code
    )
    if representative is None:
        candidates = await location_service.list_locations(country_code=country_code, state_code=state_code)
        return StateWeatherResponse(
            message=(
                f"No representative location is configured for {state_code}, {country_code}. "
                "Select one of the supported locations below."
            ),
            supported_locations=[LocationOut.from_row(loc) for loc in candidates],
        )

    try:
        result, location = await weather_service.get_current_by_location_id(representative.location_id)
    except WeatherProviderError as exc:
        raise HTTPException(status_code=502, detail="Weather provider unavailable") from exc

    return StateWeatherResponse(
        representative_location=LocationOut.from_row(location),
        weather=WeatherObservationOut.model_validate(result.observation, from_attributes=True),
        cache_status="hit" if result.cache_hit else "miss",
        disclaimer=(
            f"This result represents {location.location_name} ({location.state_name}), "
            f"the configured representative location for {state_code}, {country_code} - "
            "not an average or forecast for the entire state/province."
        ),
    )
