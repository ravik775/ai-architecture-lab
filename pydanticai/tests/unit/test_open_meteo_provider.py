from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from app.config.settings import HttpClientSettings, WeatherProviderSettings
from app.domain.errors import WeatherProviderError, WeatherProviderTimeoutError
from app.domain.models import CollectionType, ProviderName
from app.infrastructure.weather.open_meteo_provider import OpenMeteoWeatherProvider

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _sample_response(*, unix_time: int = 1_700_000_000) -> dict:
    return {
        "latitude": 17.38,
        "longitude": 78.49,
        "current": {
            "time": unix_time,
            "temperature_2m": 31.2,
            "relative_humidity_2m": 55.0,
            "apparent_temperature": 33.8,
            "precipitation": 0.0,
            "weather_code": 1,
            "wind_speed_10m": 12.4,
            "wind_direction_10m": 220.0,
        },
    }


@pytest.fixture
def fast_http_settings() -> HttpClientSettings:
    return HttpClientSettings(max_retries=2, backoff_base_seconds=0.01, backoff_max_seconds=0.02)


@pytest.fixture
def provider_settings() -> WeatherProviderSettings:
    return WeatherProviderSettings()


async def _make_provider(fast_http_settings, provider_settings) -> OpenMeteoWeatherProvider:
    client = httpx.AsyncClient()
    return OpenMeteoWeatherProvider(client, provider_settings, fast_http_settings)


@respx.mock
async def test_maps_fields_for_general_forecast(fast_http_settings, provider_settings):
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_sample_response()))
    provider = await _make_provider(fast_http_settings, provider_settings)

    obs = await provider.get_current_weather(
        latitude=17.385, longitude=78.4867, timezone="Asia/Kolkata", provider_preference="open_meteo"
    )

    assert route.calls.last.request.url.params["models"] == "best_match"
    assert obs.provider == ProviderName.OPEN_METEO_FORECAST
    assert obs.model == "best_match"
    assert obs.temperature_c == 31.2
    assert obs.humidity_percent == 55.0
    assert obs.collection_type == CollectionType.ON_DEMAND
    assert obs.local_date == date(2023, 11, 15)  # UTC 22:13 + IST (UTC+5:30) rolls into the next day


@respx.mock
async def test_meteoswiss_selected_when_in_domain(fast_http_settings, provider_settings):
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_sample_response()))
    provider = await _make_provider(fast_http_settings, provider_settings)

    obs = await provider.get_current_weather(
        latitude=47.3769, longitude=8.5417, timezone="Europe/Zurich", provider_preference="meteoswiss"
    )

    assert route.calls.last.request.url.params["models"] == "meteoswiss_icon_seamless"
    assert obs.provider == ProviderName.OPEN_METEO_METEOSWISS


@respx.mock
async def test_meteoswiss_falls_back_outside_domain(fast_http_settings, provider_settings):
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_sample_response()))
    provider = await _make_provider(fast_http_settings, provider_settings)

    # New York City is nowhere near the MeteoSwiss domain.
    obs = await provider.get_current_weather(
        latitude=40.7128, longitude=-74.0060, timezone="America/New_York", provider_preference="meteoswiss"
    )

    assert route.calls.last.request.url.params["models"] == "best_match"
    assert obs.provider == ProviderName.OPEN_METEO_FORECAST


@respx.mock
async def test_retries_on_5xx_then_succeeds(fast_http_settings, provider_settings):
    route = respx.get(FORECAST_URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=_sample_response())]
    )
    provider = await _make_provider(fast_http_settings, provider_settings)

    obs = await provider.get_current_weather(latitude=1.0, longitude=1.0, timezone="UTC")

    assert route.call_count == 2
    assert obs.temperature_c == 31.2


@respx.mock
async def test_no_retry_on_client_error(fast_http_settings, provider_settings):
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(400, json={"error": True}))
    provider = await _make_provider(fast_http_settings, provider_settings)

    with pytest.raises(WeatherProviderError):
        await provider.get_current_weather(latitude=1.0, longitude=1.0, timezone="UTC")

    assert route.call_count == 1


@respx.mock
async def test_exhausted_retries_on_timeout_raises_timeout_error(fast_http_settings, provider_settings):
    route = respx.get(FORECAST_URL).mock(side_effect=httpx.ConnectTimeout("boom"))
    provider = await _make_provider(fast_http_settings, provider_settings)

    with pytest.raises(WeatherProviderTimeoutError):
        await provider.get_current_weather(latitude=1.0, longitude=1.0, timezone="UTC")

    assert route.call_count == fast_http_settings.max_retries + 1


@respx.mock
async def test_get_daily_weather_tags_collection_type(fast_http_settings, provider_settings):
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_sample_response()))
    provider = await _make_provider(fast_http_settings, provider_settings)

    obs = await provider.get_daily_weather(
        latitude=1.0, longitude=1.0, timezone="UTC", target_date=date(2023, 11, 14)
    )

    assert obs.collection_type == CollectionType.DAILY_BATCH
