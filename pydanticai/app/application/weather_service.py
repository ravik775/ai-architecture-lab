"""Low-latency current-weather path: cache -> coalesce -> provider.

This service NEVER touches the LLM/agent - it is the deterministic path
used directly by `/v1/weather/current*`, by the UI's "Current Weather" tab,
and by the agent's `get_current_weather` tool (so all three share identical
caching/coalescing/latency behavior).
"""
from __future__ import annotations

import asyncio
import logging
import time

from app.config.settings import CacheSettings, HttpClientSettings
from app.domain.errors import LocationNotFoundError, WeatherProviderError, WeatherProviderTimeoutError
from app.domain.models import WeatherObservation
from app.domain.protocols import WeatherCache, WeatherProvider
from app.infrastructure.database.models import ConfiguredLocationRow
from app.infrastructure.database.repositories import LocationRepository
from app.infrastructure.database.session import Database
from app.observability.metrics import (
    active_outbound_requests,
    cache_hits_total,
    cache_misses_total,
    open_meteo_failures_total,
    open_meteo_request_duration_seconds,
    weather_request_duration_seconds,
    weather_requests_total,
)
from app.observability.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class WeatherResult:
    __slots__ = ("observation", "cache_hit", "latency_ms")

    def __init__(self, observation: WeatherObservation, cache_hit: bool, latency_ms: float) -> None:
        self.observation = observation
        self.cache_hit = cache_hit
        self.latency_ms = latency_ms


class WeatherService:
    def __init__(
        self,
        provider: WeatherProvider,
        cache: WeatherCache,
        db: Database,
        location_repository: LocationRepository,
        cache_settings: CacheSettings,
        http_settings: HttpClientSettings,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._db = db
        self._location_repository = location_repository
        self._cache_settings = cache_settings
        self._http_settings = http_settings
        self._inflight: dict[str, asyncio.Task[WeatherObservation]] = {}
        self._inflight_lock = asyncio.Lock()

    async def get_current_by_location_id(self, location_id: str) -> tuple[WeatherResult, ConfiguredLocationRow]:
        async with self._db.session() as session:
            location = await self._location_repository.get_location(session, location_id)
        if location is None or not location.active:
            raise LocationNotFoundError(location_id)

        result = await self._get_current(
            cache_key=f"loc:{location.location_id}",
            latitude=location.latitude,
            longitude=location.longitude,
            timezone=location.timezone,
            provider_preference=location.provider_preference,
            location_id=location.location_id,
            path_type="location",
        )
        return result, location

    async def get_current_by_coordinates(
        self, *, latitude: float, longitude: float, timezone: str
    ) -> WeatherResult:
        cache_key = f"coord:{latitude:.4f}:{longitude:.4f}:{timezone}"
        return await self._get_current(
            cache_key=cache_key,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            provider_preference="open_meteo",
            location_id=None,
            path_type="coordinates",
        )

    async def _get_current(
        self,
        *,
        cache_key: str,
        latitude: float,
        longitude: float,
        timezone: str,
        provider_preference: str,
        location_id: str | None,
        path_type: str,
    ) -> WeatherResult:
        started = time.perf_counter()

        with tracer.start_as_current_span("weather_service.get_current") as span:
            span.set_attribute("weather.path_type", path_type)
            span.set_attribute("weather.provider_preference", provider_preference)

            cached = await self._cache.get(cache_key)
            if cached is not None:
                cache_hits_total.inc()
                span.set_attribute("weather.cache_status", "hit")
                latency_ms = (time.perf_counter() - started) * 1000
                weather_requests_total.labels(path_type=path_type, cache_status="hit").inc()
                weather_request_duration_seconds.labels(path_type=path_type).observe(latency_ms / 1000)
                return WeatherResult(cached, cache_hit=True, latency_ms=latency_ms)

            cache_misses_total.inc()
            span.set_attribute("weather.cache_status", "miss")

            observation = await self._get_or_coalesce(
                cache_key,
                latitude=latitude,
                longitude=longitude,
                timezone=timezone,
                provider_preference=provider_preference,
                location_id=location_id,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            weather_requests_total.labels(path_type=path_type, cache_status="miss").inc()
            weather_request_duration_seconds.labels(path_type=path_type).observe(latency_ms / 1000)
            return WeatherResult(observation, cache_hit=False, latency_ms=latency_ms)

    async def _get_or_coalesce(self, cache_key: str, **provider_kwargs) -> WeatherObservation:
        async with self._inflight_lock:
            task = self._inflight.get(cache_key)
            if task is None:
                task = asyncio.create_task(self._fetch_and_cache(cache_key, provider_kwargs))
                self._inflight[cache_key] = task
        try:
            return await task
        finally:
            async with self._inflight_lock:
                if self._inflight.get(cache_key) is task:
                    del self._inflight[cache_key]

    async def _fetch_and_cache(self, cache_key: str, provider_kwargs: dict) -> WeatherObservation:
        provider_preference = provider_kwargs.get("provider_preference", "open_meteo")
        started = time.perf_counter()
        active_outbound_requests.inc()
        try:
            with tracer.start_as_current_span("weather_service.provider_fetch") as span:
                span.set_attribute("weather.provider_preference", provider_preference)
                try:
                    observation = await asyncio.wait_for(
                        self._provider.get_current_weather(**provider_kwargs),
                        timeout=self._http_settings.total_latency_budget_seconds,
                    )
                except TimeoutError as exc:
                    open_meteo_failures_total.labels(
                        provider=provider_preference, error_type="TotalBudgetExceeded"
                    ).inc()
                    raise WeatherProviderTimeoutError(
                        f"current-weather request exceeded {self._http_settings.total_latency_budget_seconds}s budget"
                    ) from exc
                except WeatherProviderError as exc:
                    open_meteo_failures_total.labels(
                        provider=provider_preference, error_type=type(exc).__name__
                    ).inc()
                    raise
        finally:
            active_outbound_requests.dec()
            open_meteo_request_duration_seconds.labels(provider=provider_preference).observe(
                time.perf_counter() - started
            )

        await self._cache.set(cache_key, observation)
        return observation
