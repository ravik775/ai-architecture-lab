"""OpenMeteoWeatherProvider - the sole `WeatherProvider` implementation.

Provider/model selection is config-driven (see `WeatherProviderSettings`):
- `provider_preference="meteoswiss"` + coordinates inside the configured
  MeteoSwiss bounding box -> `models=meteoswiss_icon_seamless` on the same
  `/v1/forecast` endpoint (there is no separate MeteoSwiss base URL - see
  Phase 2 correction).
- Anything else -> `models=best_match` (Open-Meteo's own automatic
  best-match selection across its global model blend - confirmed via a
  live 400 response that the commonly-cited `models=auto` is NOT a valid
  value: "Cannot initialize MultiDomains from invalid String value auto").
- `meteoswiss` requested but outside the bounding box: NEVER silently used
  outside its area - falls back to the general selector and the fallback
  is logged with a warning, not swallowed.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config.settings import HttpClientSettings, WeatherProviderSettings
from app.domain.errors import WeatherProviderError, WeatherProviderTimeoutError, WeatherProviderUnavailableError
from app.domain.models import CollectionType, ProviderName, WeatherObservation

logger = logging.getLogger(__name__)

_CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,"
    "precipitation,weather_code,wind_speed_10m,wind_direction_10m"
)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.ConnectError | httpx.ReadError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


class OpenMeteoWeatherProvider:
    """Implements `app.domain.protocols.WeatherProvider`."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        provider_settings: WeatherProviderSettings,
        http_settings: HttpClientSettings,
    ) -> None:
        self._client = http_client
        self._provider_settings = provider_settings
        self._http_settings = http_settings

    def _in_meteoswiss_domain(self, latitude: float, longitude: float) -> bool:
        s = self._provider_settings
        return (
            s.meteoswiss_lat_min <= latitude <= s.meteoswiss_lat_max
            and s.meteoswiss_lon_min <= longitude <= s.meteoswiss_lon_max
        )

    def _resolve_model_selector(
        self, *, latitude: float, longitude: float, provider_preference: str
    ) -> tuple[str, ProviderName]:
        s = self._provider_settings
        if provider_preference == "meteoswiss":
            if self._in_meteoswiss_domain(latitude, longitude):
                return s.meteoswiss_model_selector, ProviderName.OPEN_METEO_METEOSWISS
            logger.warning(
                "meteoswiss requested outside supported domain (lat=%s, lon=%s); "
                "falling back to general auto model - never used silently",
                latitude,
                longitude,
            )
        return s.general_model_selector, ProviderName.OPEN_METEO_FORECAST

    async def _fetch(
        self,
        *,
        latitude: float,
        longitude: float,
        timezone: str,
        provider_preference: str,
        collection_type: CollectionType,
        location_id: str | None,
    ) -> WeatherObservation:
        model_selector, provider = self._resolve_model_selector(
            latitude=latitude, longitude=longitude, provider_preference=provider_preference
        )
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": _CURRENT_FIELDS,
            "models": model_selector,
            "timeformat": "unixtime",
        }

        async def _do_request() -> httpx.Response:
            response = await self._client.get(
                self._provider_settings.open_meteo_forecast_url, params=params
            )
            response.raise_for_status()
            return response

        try:
            retrying = AsyncRetrying(
                stop=stop_after_attempt(self._http_settings.max_retries + 1),
                wait=wait_exponential_jitter(
                    initial=self._http_settings.backoff_base_seconds,
                    max=self._http_settings.backoff_max_seconds,
                ),
                retry=retry_if_exception(_is_transient),
                reraise=True,
            )
            response = await retrying(_do_request)
        except TimeoutError as exc:
            raise WeatherProviderTimeoutError(str(exc)) from exc
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            raise WeatherProviderTimeoutError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise WeatherProviderUnavailableError(str(exc)) from exc
            raise WeatherProviderError(f"Open-Meteo rejected request: {exc}") from exc
        except httpx.HTTPError as exc:
            raise WeatherProviderError(str(exc)) from exc

        payload = response.json()
        current = payload["current"]
        observation_time_utc = datetime.fromtimestamp(current["time"], tz=UTC)
        local_date = observation_time_utc.astimezone(ZoneInfo(timezone)).date()

        return WeatherObservation(
            location_id=location_id,
            latitude=latitude,
            longitude=longitude,
            observation_time_utc=observation_time_utc,
            local_date=local_date,
            temperature_c=current["temperature_2m"],
            apparent_temperature_c=current["apparent_temperature"],
            humidity_percent=current["relative_humidity_2m"],
            precipitation_mm=current["precipitation"],
            weather_code=current["weather_code"],
            wind_speed_kmh=current["wind_speed_10m"],
            wind_direction_deg=current["wind_direction_10m"],
            provider=provider,
            model=model_selector,
            unit_system="metric",
            collection_type=collection_type,
        )

    async def get_current_weather(
        self,
        *,
        latitude: float,
        longitude: float,
        timezone: str,
        provider_preference: str = "open_meteo",
        location_id: str | None = None,
    ) -> WeatherObservation:
        return await self._fetch(
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            provider_preference=provider_preference,
            collection_type=CollectionType.ON_DEMAND,
            location_id=location_id,
        )

    async def get_daily_weather(
        self,
        *,
        latitude: float,
        longitude: float,
        timezone: str,
        target_date: date,
        provider_preference: str = "open_meteo",
        location_id: str | None = None,
    ) -> WeatherObservation:
        observation = await self._fetch(
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            provider_preference=provider_preference,
            collection_type=CollectionType.DAILY_BATCH,
            location_id=location_id,
        )
        if observation.local_date != target_date:
            logger.warning(
                "daily collection for %s: observed local_date=%s differs from target_date=%s "
                "(collection likely ran outside the intended end-of-day window)",
                location_id,
                observation.local_date,
                target_date,
            )
        return observation
