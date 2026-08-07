"""Verifies WeatherService emits a correct parent/child span tree, using an
in-memory exporter wired directly into the module (bypasses the global OTel
provider singleton, which other tests in the suite may have already set -
see comment below for why this is the deterministic approach).
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import app.application.weather_service as weather_service_module
from app.config.settings import CacheSettings, HttpClientSettings
from app.domain.models import CollectionType, ProviderName, WeatherObservation
from app.application.weather_service import WeatherService


class _FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, WeatherObservation] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: WeatherObservation) -> None:
        self.store[key] = value


class _FakeProvider:
    async def get_current_weather(self, **kwargs) -> WeatherObservation:
        return WeatherObservation(
            latitude=kwargs["latitude"],
            longitude=kwargs["longitude"],
            observation_time_utc=datetime.now(UTC),
            local_date=date.today(),
            temperature_c=20.0,
            apparent_temperature_c=19.0,
            humidity_percent=40.0,
            precipitation_mm=0.0,
            weather_code=0,
            wind_speed_kmh=5.0,
            wind_direction_deg=90.0,
            provider=ProviderName.OPEN_METEO_FORECAST,
            model="auto",
            unit_system="metric",
            collection_type=CollectionType.ON_DEMAND,
        )


@pytest.fixture()
def in_memory_exporter(monkeypatch):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    test_tracer = provider.get_tracer("test")
    monkeypatch.setattr(weather_service_module, "tracer", test_tracer)
    return exporter


async def test_weather_service_span_tree_has_correct_parent_child(in_memory_exporter):
    service = WeatherService(
        provider=_FakeProvider(),
        cache=_FakeCache(),
        db=None,
        location_repository=None,
        cache_settings=CacheSettings(),
        http_settings=HttpClientSettings(),
    )

    await service.get_current_by_coordinates(latitude=1.0, longitude=2.0, timezone="UTC")

    spans = in_memory_exporter.get_finished_spans()
    names = {s.name for s in spans}
    assert names == {"weather_service.get_current", "weather_service.provider_fetch"}

    parent = next(s for s in spans if s.name == "weather_service.get_current")
    child = next(s for s in spans if s.name == "weather_service.provider_fetch")

    assert child.parent is not None
    assert child.parent.span_id == parent.context.span_id
    assert child.context.trace_id == parent.context.trace_id


async def test_weather_service_cache_hit_emits_single_span(in_memory_exporter):
    cache = _FakeCache()
    service = WeatherService(
        provider=_FakeProvider(),
        cache=cache,
        db=None,
        location_repository=None,
        cache_settings=CacheSettings(),
        http_settings=HttpClientSettings(),
    )

    await service.get_current_by_coordinates(latitude=1.0, longitude=2.0, timezone="UTC")
    in_memory_exporter.clear()

    # Second call should hit the cache and never create a provider_fetch span.
    await service.get_current_by_coordinates(latitude=1.0, longitude=2.0, timezone="UTC")

    spans = in_memory_exporter.get_finished_spans()
    assert [s.name for s in spans] == ["weather_service.get_current"]
