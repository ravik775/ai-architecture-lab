from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest


async def _insert_observation(location_id: str, day: date, temperature: float) -> None:
    from app.config import get_settings
    from app.infrastructure.database.repositories import ObservationRepository
    from app.infrastructure.database.session import Database

    settings = get_settings()
    db = Database(settings.database)
    repo = ObservationRepository()
    async with db.session() as session:
        await repo.upsert_observation(
            session,
            location_id=location_id,
            observation_date=day,
            observation_timestamp_utc=datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc),
            local_date=day,
            temperature_c=temperature,
            apparent_temperature_c=temperature,
            humidity_percent=50.0,
            precipitation_mm=0.0,
            weather_code=0,
            wind_speed_kmh=1.0,
            wind_direction_deg=1.0,
            provider="open-meteo-forecast",
            model="auto",
            unit_system="metric",
            collection_type="daily_batch",
        )
        await session.commit()
    await db.dispose()


@pytest.fixture()
def seeded_history(app_client):
    base = date(2024, 1, 1)
    for i in range(3):
        asyncio.run(_insert_observation("hyderabad", base + timedelta(days=i), 20.0 + i))
    asyncio.run(_insert_observation("mumbai", base, 25.0))
    return base


def test_history_filtered_by_location(app_client, seeded_history):
    resp = app_client.get("/v1/weather/history", params={"location_id": "hyderabad"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert all(item["location_id"] == "hyderabad" for item in body["items"])


def test_history_pagination(app_client, seeded_history):
    resp = app_client.get("/v1/weather/history", params={"location_id": "hyderabad", "page_size": 1, "page": 1})
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["total"] == 3
    assert body["total_pages"] == 3


def test_history_date_range_filter(app_client, seeded_history):
    base = seeded_history
    resp = app_client.get(
        "/v1/weather/history",
        params={
            "location_id": "hyderabad",
            "start_date": base.isoformat(),
            "end_date": base.isoformat(),
        },
    )
    body = resp.json()
    assert body["total"] == 1


def test_history_date_range_too_large_rejected(app_client, monkeypatch):
    resp = app_client.get(
        "/v1/weather/history",
        params={
            "location_id": "hyderabad",
            "start_date": "2020-01-01",
            "end_date": "2024-01-01",
        },
    )
    assert resp.status_code == 400


def test_history_page_size_clamped_to_security_max(app_client, seeded_history):
    resp = app_client.get("/v1/weather/history", params={"page_size": 500})
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_size"] <= 100
